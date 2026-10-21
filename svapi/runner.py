"""Build a JSON model in a newly owned, verified SystemView process."""
import ctypes as C
from ctypes import wintypes as W
import hashlib, json, re, shutil, subprocess, time, sys
from types import SimpleNamespace
from pathlib import Path
from svctl import BridgeError, Session, Win, launch
from .model import Model
from .native import ENGINE_SHA
from svsettings import get_engine
from .verify import verify_waveforms, verify_spectrum, verify_complex_fft
from .render import render_plot

ENGINE=None


def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def check_idle(win):
    # SystemView may hand a file to an existing process and exit successfully.
    # Enumerate candidate process names first; never launch into another session.
    class Process(C.Structure):
        _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),
                  ('heap',C.c_size_t),('module',W.DWORD),('threads',W.DWORD),
                  ('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]
    k=win.k;k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    for name in ['Process32FirstW','Process32NextW']:
        getattr(k,name).argtypes=[W.HANDLE,C.POINTER(Process)];getattr(k,name).restype=W.BOOL
    snap=k.CreateToolhelp32Snapshot(2,0)
    if snap==C.c_void_p(-1).value:raise BridgeError('Cannot check for an existing SystemView process')
    try:
        entry=Process();entry.size=C.sizeof(entry);ok=k.Process32FirstW(snap,C.byref(entry))
        while ok:
            if entry.exe.casefold()==ENGINE.name.casefold():
                identity=win.identity(entry.pid)
                if identity['exe'].casefold()==str(ENGINE).casefold():
                    raise BridgeError(f'SystemView is already running (PID {entry.pid}); close it before a new build. Existing work was not changed.')
            ok=k.Process32NextW(snap,C.byref(entry))
    finally:k.CloseHandle(snap)


def start_blank(out):
    global ENGINE
    ENGINE=get_engine()
    if hashlib.sha256(ENGINE.read_bytes()).hexdigest()!=ENGINE_SHA:
        raise BridgeError('This native adapter requires the pinned ELANIX SystemView 5 Build046 executable')
    win=Win();check_idle(win)
    blank=out/'blank.svu'
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    process=subprocess.Popen([str(ENGINE)],cwd=str(ENGINE.parent),startupinfo=startup)
    state={**win.identity(process.pid),'project':None,'generated':True}
    state_path=out/'session.json';write_json(state_path,state)
    session=Session(state_path);started=time.monotonic();quiet=started;deadline=started+45
    # Tips are opened by VB6's startup timer after the design form first appears.
    # Let that timer finish and close only these two known startup notices.
    while time.monotonic()<deadline:
        if process.poll() is not None:raise BridgeError(f'New SystemView process exited during startup ({process.returncode})')
        if session.dismiss_startup_notices():quiet=time.monotonic()
        for hwnd in win.windows(process.pid):
            if win.cls(hwnd)=='#32770':
                text=' | '.join(win.text(c) for c in win.children(hwnd))
                if 'error loading SystemView' in text:raise BridgeError('SystemView desktop startup error: '+text)
        try:
            frame=session.frame('design')
            ready=win.u.IsWindowEnabled(frame) and any(win.normalize(item['path'][0])=='system' for item in win.menus(frame))
        except BridgeError:ready=False
        if not ready:quiet=time.monotonic()
        if ready and time.monotonic()-started>=10.0 and time.monotonic()-quiet>=2.0:
            # A new no-file process starts with an empty native design. Do not
            # queue New/Save while VB6 is replacing its startup form. The first
            # add verifies that exactly one token exists; no template is used.
            if win.text(frame).startswith('SystemView - '):raise BridgeError('Unexpected automatically opened project at startup')
            return session
        time.sleep(.15)
    raise BridgeError('Timed out starting a new blank SystemView model; see session.json')


def close_generated(session):
    if not session.state.get('generated'):raise BridgeError('Refusing automatic close of a session not created by the builder')
    try:frame=session.frame('design')
    except BridgeError:
        masters=[h for h in session.win.windows(session.state['pid']) if session.win.cls(h)=='ThunderRT6Main']
        if len(masters)!=1:raise BridgeError('Cannot identify generated application root')
        frame=masters[0]
    session.win.post(session.handle(frame),0x10)
    def exited():
        try:
            if session.win.identity(session.state['pid'])!={k:session.state[k] for k in ['pid','created','exe']}:return True
        except BridgeError:return True
        return False
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if exited():return {'closed':True,'orphan_cleanup':False}
        time.sleep(.08)
    visible=[h for h in session.win.windows(session.state['pid'])
             if session.win.u.IsWindowVisible(h) and
             (session.win.cls(h) in ['ThunderRT6FormDC','ThunderRT6MDIForm','#32770'])]
    if visible:raise BridgeError('Generated application still has a visible form or dialog; automatic cleanup refused')
    # Some no-file launches leave only VB6/DDE framework windows after all UI
    # forms unload. The generated process has no visible document or prompt.
    # Revalidate its exact identity and terminate only this owned orphan.
    expected={k:session.state[k] for k in ['pid','created','exe']}
    if session.win.identity(session.state['pid'])!=expected:raise BridgeError('Cleanup process identity changed')
    handle=session.win.k.OpenProcess(0x1001,False,session.state['pid'])
    if not handle:raise BridgeError('Cannot open generated orphan for cleanup')
    try:
        if session.win.identity(session.state['pid'])!=expected:raise BridgeError('Cleanup identity changed')
        session.win.k.TerminateProcess.argtypes=[W.HANDLE,W.UINT];session.win.k.TerminateProcess.restype=W.BOOL
        if not session.win.k.TerminateProcess(handle,0x53563500):raise BridgeError('Cannot close generated orphan')
    finally:session.win.k.CloseHandle(handle)
    session.wait(exited,'owned orphan process to exit',5)
    return {'closed':True,'orphan_cleanup':True}


KINDS={'source':0,'adder':2,'operator':4,'function':5,'multiplier':6,'sink':7,'logic':11}


def validate_recipe(recipe):
    if not isinstance(recipe,dict) or recipe.get('schema')!=1:raise ValueError('Expected recipe schema 1')
    nodes=recipe['nodes'];ids=[n['id'] for n in nodes]
    if len(nodes)==0 or len(nodes)>100 or len(set(ids))!=len(ids):raise ValueError('Recipe requires 1..100 unique node IDs')
    for n in nodes:
        if n['kind'] not in KINDS:raise ValueError('Unsupported node reservoir: '+n['kind'])
        if len(n['at'])!=2 or not 0<=n['at'][0]<=2000 or not 0<=n['at'][1]<=1200:raise ValueError('Node position outside supported canvas')
        if n['kind'] not in ['adder','multiplier'] and 'choice' not in n:raise ValueError('Node requires a library choice')
        if 'choice' in n and (not isinstance(n['choice'],str) or not n['choice'].strip()):raise ValueError('Recipe choices must be actual nonempty library labels')
        if n['kind'] in ['adder','multiplier'] and 'choice' in n:raise ValueError('Adder/multiplier use their native default definition')
        if any(str(k) not in ['21','42','44','46','48','50','52','54','56','58','60'] or not isinstance(v,(int,float))
               for k,v in n.get('params',{}).items()):raise ValueError('Only native numeric parameter fields are supported')
    for e in recipe['edges']:
        if e['from'] not in ids or e['to'] not in ids:raise ValueError('Edge references unknown node')
    for name,node in recipe['outputs'].items():
        if not re.fullmatch(r'[a-z0-9-]+',name) or node not in ids:raise ValueError('Invalid output name/node')
        if nodes[ids.index(node)]['kind']!='sink':raise ValueError('Output must reference a sink')
    timing=recipe['timing']
    if not 0<timing['fs']<=1e7 or not timing['stop']>timing.get('start',0):raise ValueError('Invalid timing')
    if any(name not in recipe['outputs'] for name in recipe.get('spectra',[])):raise ValueError('Spectrum references unknown output')
    seen=set()
    for view in recipe.get('fft_views',[]):
        if not re.fullmatch(r'[a-z0-9-]+',view['name']) or view['name'] in seen:raise ValueError('Invalid or duplicate FFT view name')
        seen.add(view['name'])
        if view['signal'] not in recipe['outputs']:raise ValueError('FFT view references unknown output')
        if not view['xlim'][0]<view['xlim'][1] or not view['ylim'][0]<view['ylim'][1]:raise ValueError('Invalid FFT view ranges')


def build(recipe_path,output,keep_open=False):
    recipe_path=Path(recipe_path).resolve(strict=True)
    recipe=json.loads(recipe_path.read_text(encoding='utf-8'));validate_recipe(recipe)
    out=Path(output).resolve()
    if out.exists():raise BridgeError('Build requires a new output directory; nothing was overwritten')
    out.mkdir(parents=True);write_json(out/'recipe.json',recipe)
    session=None;model=None;report={'passed':False,'recipe':recipe['name'],'output':str(out)}
    try:
        session=start_blank(out);model=Model(session)
        tokens={}
        for spec in recipe['nodes']:
            token=model.add(KINDS[spec['kind']],*spec['at']);tokens[spec['id']]=token
            if spec['kind'] not in ['adder','multiplier']:
                model.define(token,spec['kind'],spec['choice'],spec.get('params'))
            print(f"node {spec['id']} -> {token}",file=sys.stderr,flush=True)
        for e in recipe['edges']:model.connect(tokens[e['from']],tokens[e['to']],e.get('port'),e.get('out_port'))
        model.timing(**recipe['timing'])
        report['tokens']=session.tokens()
        if len(report['tokens'])!=len(recipe['nodes']):raise BridgeError('Native token count differs from recipe')
        report['model']=session.save_as(out/'model.svu')
        # VB6 can retain stale forms/controls after many library dialogs. Commit
        # the model, release the native bridge, then simulate a freshly loaded
        # copy in a new owned process. No numerical state is transferred manually.
        write_json(out/'construction-session.json',session.state)
        construction_log=model.log
        model.n.stop();report['construction_cleanup']=close_generated(session);check_idle(Win())
        launch(SimpleNamespace(project=str(out/'model.svu'),exe=str(ENGINE),state=str(out/'session.json'),timeout=35))
        session=Session(out/'session.json');session.state['generated']=True;write_json(session.state_path,session.state)
        model=Model(session,len(recipe['nodes']));model.log=construction_log
        sinks=[tokens[n['id']] for n in recipe['nodes'] if n['kind']=='sink']
        plots=model.run(len(sinks));paths={};exports={};plot_ids={}
        for name,node in recipe['outputs'].items():
            sink=tokens[node];matched=[p for p in plots if re.fullmatch(rf'w\d+: Sink {sink}',p['text'])]
            if len(matched)!=1:raise BridgeError(f'Expected one waveform for Sink {sink}')
            plot=matched[0]['text'].split(':',1)[0];plot_ids[name]=plot;paths[name]=out/(name+'.csv')
            exports[name]=session.export(plot,paths[name]);print('export '+name,file=sys.stderr,flush=True)
        report['waveforms']=exports
        checks=verify_waveforms(recipe.get('verification'),paths,recipe['timing'],recipe.get('verification_options'));report['waveform_checks']=checks
        if not checks['passed']:raise BridgeError('Waveform numerical acceptance failed')
        report['spectra']={}
        for name in recipe.get('spectra',[]):
            result=model.spectrum(plot_ids[name],out/(name+'-spectrum.csv'))
            result['checks']=verify_spectrum(paths[name],result['data']['path'],recipe['timing']['fs'])
            report['spectra'][name]=result
            if not result['checks']['passed']:raise BridgeError('Spectrum numerical acceptance failed: '+name)
            print('spectrum '+name,file=sys.stderr,flush=True)
        report['fft_views']={}
        for view in recipe.get('fft_views',[]):
            name=view['name'];signal=view['signal']
            result=model.complex_fft(plot_ids[signal],out/(name+'-full.csv'))
            result['checks']=verify_complex_fft(paths[signal],result['data']['path'],recipe['timing']['fs'])
            if not result['checks']['passed']:raise BridgeError('Complex FFT numerical acceptance failed: '+name)
            result['view']=model.scale_view(result['plot'],view['xlim'],view['ylim'])
            previous=model.color_exports(True)
            try:
                result['image']=session.export_image(result['view']['plot'],out/(name+'.wmf'))
                result['png']=render_plot(session,result['view']['plot'],out/(name+'.png'))
            finally:model.color_exports(previous)
            report['fft_views'][name]=result;print('native FFT view '+name,file=sys.stderr,flush=True)
        model.close_analysis();report['saved_results']=session.save_as(out/'model-with-results.svu')
        model.save_log(out/'operations.json');report['passed']=True;write_json(out/'verification.json',report)
        model.n.stop()
        if not keep_open:report['simulation_cleanup']=close_generated(session)
        write_json(out/'verification.json',report)
        return report
    except BaseException as error:
        report['passed']=False;report['error']=str(error);write_json(out/'verification.json',report)
        if model:model.save_log(out/'operations.json')
        # Keep the generated process and native feedback for diagnosis on failure.
        # Never silently dismiss an unexpected dialog or kill a desktop process.
        raise
