"""Numerical acceptance checks on data exported by SystemView, without NumPy."""
import csv, math
from pathlib import Path


def read_xy(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    x, y = [float(r['x']) for r in rows], [float(r['y']) for r in rows]
    if not x or not all(math.isfinite(v) for v in x + y):
        raise ValueError(f'Invalid numerical export: {path}')
    return x, y


def verify_waveforms(kind, paths, timing, options=None):
    data = {key: read_xy(path) for key, path in paths.items()}
    fs, start, stop = timing['fs'], timing.get('start', 0), timing['stop']
    count = round((stop-start)*fs)+1
    grids = {name: len(x) == count and max(abs(t-(start+i/fs)) for i,t in enumerate(x)) < 1e-12
             for name, (x, _) in data.items()}
    y = {name: pair[1] for name, pair in data.items()}
    checks = {'sample_count': count, 'time_grids': grids}
    if kind == 'nrz-rz':
        u,c,p,neg,b,bn = [y[k] for k in ['unipolar-nrz','clock','unipolar-rz','negative-rz','bipolar-rz','bipolar-nrz']]
        errors = {
            'unipolar_rz': max(abs(v-float(a>.5 and z>.5)) for a,z,v in zip(u,c,p)),
            'negative_rz': max(abs(v+float(a<=.5 and z>.5)) for a,z,v in zip(u,c,neg)),
            'inverted_nrz': max(abs(v-float(a<=.5)) for a,v in zip(u,y['inverted-nrz'])),
            'bipolar_rz_sum': max(abs(v-a-z) for a,z,v in zip(p,neg,b)),
            'bipolar_nrz': max(abs(v-(a-1)) for a,v in zip(u,bn)),
            'bipolar_rz_product': max(abs(v-a*z) for a,z,v in zip(bn,c,b)),
        }
        checks['max_errors'] = errors
        checks['passed'] = all(grids.values()) and max(errors.values()) == 0
    elif kind == 'multiply':
        error = max(abs(v-a*b) for a,b,v in zip(y['pn'],y['pulse'],y['product']))
        checks.update(max_product_error=error, passed=all(grids.values()) and error==0)
    elif kind == 'ami':
        # Test every sample away from switching instants, plus each bit center.
        # Derivative gain 1 yields amplitude Fs; Hold has small FP roundoff.
        per_bit = round(fs/50)
        if not math.isclose(per_bit,fs/50):
            raise ValueError('AMI acceptance recipe requires an integer samples/bit')
        errors, signs, expected = [], [], 0
        startup=int((options or {}).get('startup_symbols',0))
        if startup not in [0,1]:raise ValueError('Only the explicitly declared zero/one-symbol startup is supported')
        startup_error=max((abs(v) for v in y['output'][:startup*per_bit]),default=0)
        max_error = 0
        for bit in range(startup,int((stop-start)*50)):
            i=bit*per_bit+per_bit//2
            mark=y['input'][i]>.5
            value=y['output'][i]
            if mark:
                expected = 1 if expected<=0 else -1
                signs.append(1 if value>0 else -1)
            target=expected*fs if mark else 0
            max_error=max(max_error,abs(value-target))
            if abs(value-target)>fs*1e-9: errors.append(bit)
            for j in range(bit*per_bit+2,min((bit+1)*per_bit-2,count)):
                max_error=max(max_error,abs(y['output'][j]-target))
        gate_error=max(abs(v-float(a>.5 and b>.5)) for a,b,v in zip(y['input'],y['clock'],y['gated-clock'])) if 'clock' in y else 0
        checks.update(nonzero_signs=signs, bad_bits=errors, max_ami_error=max_error, gate_error=gate_error,
                      startup_symbols=startup,startup_output_error=startup_error,
                      active_symbols_checked=int((stop-start)*50)-startup,
                      passed=all(grids.values()) and len(signs)>1 and not errors and
                      startup_error<fs*1e-9 and max_error<fs*1e-9 and gate_error==0 and all(a==-b for a,b in zip(signs,signs[1:])))
    else:
        checks['passed'] = all(grids.values())
    return checks


def verify_spectrum(waveform, spectrum, fs):
    _,y=read_xy(waveform);f,db=read_xy(spectrum)
    powers=[10**((v-30)/10) for v in db]
    mean_square=sum(v*v for v in y)/len(y)
    expected_dc=(sum(y)/len(y))**2
    relative=abs(sum(powers)-mean_square)/max(mean_square,1e-300)
    frequency_error=max(abs(v-i*fs/len(y)) for i,v in enumerate(f))
    return {'bins':len(f),'frequency_step':f[1]-f[0],
            'time_mean_square':mean_square,'spectrum_power':sum(powers),
            'relative_parseval_error':relative,'dc_expected':expected_dc,'dc_observed':powers[0],
            'passed':len(f)==len(y)//2+1 and relative<1e-10 and frequency_error<1e-8 and
                     math.isclose(expected_dc,powers[0],rel_tol=1e-8,abs_tol=1e-9)}


def verify_complex_fft(waveform,spectrum,fs):
    _,y=read_xy(waveform);f,mag=read_xy(spectrum);count=len(y)
    if len(f)!=count:return {'passed':False,'error':'Unexpected FFT length'}
    mid=count//2
    grid=max(abs(v-(i-mid)*fs/count) for i,v in enumerate(f))
    symmetry=max(abs(a-b) for a,b in zip(mag,reversed(mag)))
    time_power=sum(v*v for v in y)/count
    fft_power=sum(v*v for v in mag)*(fs/count)**2
    direct_errors=[]
    for i in [0,mid,mid+1,mid+13,mid+25,count-1]:
        k=i-mid;real=sum(v*math.cos(2*math.pi*k*n/count) for n,v in enumerate(y))/fs
        imag=sum(-v*math.sin(2*math.pi*k*n/count) for n,v in enumerate(y))/fs
        direct_errors.append(abs(mag[i]-math.hypot(real,imag)))
    relative=abs(fft_power-time_power)/max(time_power,1e-300)
    return {'samples':count,'bins':len(f),'x_start':f[0],'x_end':f[-1],
            'dc_magnitude':mag[mid],'dc_expected':abs(sum(y))/fs,'max_magnitude':max(mag),
            'symmetry_error':symmetry,'max_direct_dft_error':max(direct_errors),
            'relative_parseval_error':relative,
            'passed':grid<1e-8 and symmetry<1e-8 and max(direct_errors)<2e-8 and relative<1e-10}
