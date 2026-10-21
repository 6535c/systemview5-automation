"""Recipe builder for ELANIX SystemView 5 Build046. Invoked by sv.cmd model."""
import argparse,json,sys
from pathlib import Path
from svctl import BridgeError
from svapi.runner import build,write_json
from svapi.verify import verify_waveforms,verify_spectrum,verify_complex_fft

ROOT=Path(__file__).resolve().parent


def verify_directory(path):
    path=Path(path).resolve(strict=True)
    recipe=json.loads((path/'recipe.json').read_text(encoding='utf-8'))
    checks=verify_waveforms(recipe.get('verification'),{name:path/(name+'.csv') for name in recipe['outputs']},recipe['timing'],recipe.get('verification_options'))
    spectra={name:verify_spectrum(path/(name+'.csv'),path/(name+'-spectrum.csv'),recipe['timing']['fs']) for name in recipe.get('spectra',[])}
    fft_views={view['name']:verify_complex_fft(path/(view['signal']+'.csv'),path/(view['name']+'-full.csv'),recipe['timing']['fs']) for view in recipe.get('fft_views',[])}
    return {'waveforms':checks,'spectra':spectra,'fft_views':fft_views,
            'passed':checks['passed'] and all(c['passed'] for c in [*spectra.values(),*fft_views.values()])}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    cmd=commands.add_parser('build',help='Build, connect, simulate and export a JSON recipe from an empty model')
    cmd.add_argument('recipe');cmd.add_argument('--out',required=True);cmd.add_argument('--keep-open',action='store_true')
    cmd=commands.add_parser('lab1',help='Run all three experiment-1 capability acceptance recipes; no report')
    cmd.add_argument('--out',required=True)
    cmd=commands.add_parser('verify',help='Recheck exported data without launching SystemView');cmd.add_argument('directory')
    args=parser.parse_args()
    try:
        if args.command=='build':
            result=build(args.recipe,args.out,args.keep_open)
        elif args.command=='verify':result=verify_directory(args.directory)
        else:
            out=Path(args.out).resolve()
            if out.exists():raise BridgeError('lab1 requires a new output directory')
            out.mkdir(parents=True);results={}
            for name in ['nrz-rz','ami','multiply']:
                result=build(ROOT/'recipes'/(name+'.json'),out/name)
                results[name]={'passed':result['passed'],'verification':str(out/name/'verification.json')}
            result={'passed':all(r['passed'] for r in results.values()),'recipes':results}
            write_json(out/'acceptance.json',result)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False,indent=2))
        if not result['passed']:raise SystemExit(1)
    except (BridgeError,OSError,ValueError,KeyError,StopIteration) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False,indent=2));raise SystemExit(1)


if __name__=='__main__':main()
