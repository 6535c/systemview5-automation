"""Portable configuration and local-only runtime for SystemView5 Automation."""
import argparse,hashlib,json,os,shutil,sys
from pathlib import Path

VERSION='0.1.0'
ENGINE_SHA='82f1a0f823450dcf9439370c3e7c601e99da05d5aba008ab96385f41398f001f'
PACKAGE=Path(__file__).resolve().parent
BIN=PACKAGE/'bin'/'win32'
HOME=Path(os.environ.get('SV5_HOME') or (Path(os.environ.get('LOCALAPPDATA') or Path.home())/'SystemView5Automation')).resolve()
CONFIG=HOME/'config.json'


def get_engine():
    value=os.environ.get('SV5_EXE')
    if not value and CONFIG.is_file():value=json.loads(CONFIG.read_text(encoding='utf-8')).get('exe')
    if not value:raise ValueError('SystemView is not configured. Run: sv.cmd config --exe "path\\SysVu_32.exe"')
    path=Path(value).expanduser().resolve(strict=True)
    if path.name.casefold()!='sysvu_32.exe':raise ValueError('Expected ELANIX SysVu_32.exe')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=ENGINE_SHA:raise ValueError('Unsupported SystemView executable: Build046 SHA256 does not match')
    return path


def default_state():return HOME/'session.json'


def helper_manifest():
    values=json.loads((BIN/'manifest.json').read_text(encoding='utf-8'))
    if set(values)!=set(['bridge_host.exe','vbbridge.dll','SvCom.exe']):raise ValueError('Invalid helper manifest')
    for name,digest in values.items():
        if hashlib.sha256((BIN/name).read_bytes()).hexdigest()!=digest:raise ValueError('Native helper checksum mismatch: '+name)
    return values


def ensure_helpers():
    values=helper_manifest();bundle=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()[:16]
    directory=HOME/'runtime'/bundle;directory.mkdir(parents=True,exist_ok=True)
    for name,digest in values.items():
        target=directory/name
        if not target.exists():shutil.copyfile(BIN/name,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Local runtime helper was changed: '+name)
    return directory


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='SystemView5 Automation configuration')
    sub=parser.add_subparsers(dest='command',required=True)
    config=sub.add_parser('config');config.add_argument('--exe');config.add_argument('--show',action='store_true')
    sub.add_parser('doctor');sub.add_parser('version')
    args=parser.parse_args()
    try:
        if args.command=='version':result={'version':VERSION}
        elif args.command=='config':
            if args.exe:
                previous=os.environ.get('SV5_EXE');os.environ['SV5_EXE']=args.exe
                try:exe=get_engine()
                finally:
                    if previous is None:os.environ.pop('SV5_EXE',None)
                    else:os.environ['SV5_EXE']=previous
                HOME.mkdir(parents=True,exist_ok=True);CONFIG.write_text(json.dumps({'exe':str(exe)},indent=2),encoding='utf-8')
            result={'config':str(CONFIG),'exe':str(get_engine()),'engine_sha256':ENGINE_SHA}
        else:
            if sys.platform!='win32':raise ValueError('A Windows desktop session is required')
            exe=get_engine();helpers=helper_manifest()
            framework=Path(os.environ['WINDIR'])/'Microsoft.NET'/'Framework'/'v4.0.30319'
            if not (framework/'clr.dll').is_file():raise ValueError('Windows .NET Framework 4.x is required')
            result={'version':VERSION,'windows':True,'python':sys.version.split()[0],
                    'exe':str(exe),'engine_sha256':ENGINE_SHA,'helpers_verified':len(helpers),'runtime':str(HOME)}
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False,indent=2));raise SystemExit(1)


if __name__=='__main__':main()
