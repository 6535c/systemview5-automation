"""Package an explicit public allowlist; inspect text and native bytes first."""
from pathlib import Path
import argparse,hashlib,json,re,struct,zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=[
 '.gitattributes','.gitignore','README.md','LICENSE','NOTICE','llms.txt',
 'sv.cmd','sv.py','svctl.py','svmodel.py','svsettings.py','build.cmd','install.ps1',
 'svapi/__init__.py','svapi/native.py','svapi/model.py','svapi/runner.py','svapi/verify.py','svapi/render.py',
 'svapi/bridge/source/vbbridge.cpp','svapi/bridge/source/bridge_host.cpp','svapi/bridge/source/SvCom.cs',
 'bin/win32/bridge_host.exe','bin/win32/vbbridge.dll','bin/win32/SvCom.exe','bin/win32/manifest.json',
 'recipes/ami.json','recipes/nrz-rz.json','recipes/multiply.json',
 'docs/AI_USAGE.md','docs/INTERFACE.md','docs/BUILD_AND_PRIVACY.md',
 'tools/make_manifest.py','tools/package_release.py','tests/test_contract.py',
]


def audit(deny=()):
    values={}
    for relative in FILES:
        path=ROOT/relative;data=path.read_bytes()
        if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-proj-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',data):
            raise ValueError('Possible credential in '+relative)
        for term in deny:
            for encoding in ['utf-8','utf-16le','gb18030']:
                if term and term.encode(encoding,errors='ignore').lower() in data.lower():
                    raise ValueError('Private denylist match in '+relative)
        for encoding in ['utf-8','utf-16le']:
            text=data.decode(encoding,errors='ignore')
            if re.search(r'[A-Za-z]:[\\/]Users[\\/][^\\/\s"<>]+',text,re.I):raise ValueError('Personal home path in '+relative)
        if path.suffix.lower() in ['.exe','.dll']:
            if data[:2]!=b'MZ':raise ValueError('Invalid native binary: '+relative)
            pe=struct.unpack_from('<I',data,0x3c)[0]
            if data[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',data,pe+4)[0]!=0x14c:raise ValueError('Expected x86 helper: '+relative)
            optional=pe+24
            if struct.unpack_from('<H',data,optional)[0]!=0x10b:raise ValueError('Expected PE32 helper')
            debug_rva,debug_size=struct.unpack_from('<II',data,optional+96+6*8)
            if debug_rva or debug_size:
                # Optimized MSVC release links can emit POGO (type 13) section
                # layout metadata without any PDB/CodeView record. Inspect the
                # actual record types; never waive the scan for native files.
                count=struct.unpack_from('<H',data,pe+6)[0]
                table=optional+struct.unpack_from('<H',data,pe+20)[0]
                directory=None
                for i in range(count):
                    virtual_size,virtual_address,raw_size,raw_pointer=struct.unpack_from('<IIII',data,table+i*40+8)
                    if virtual_address<=debug_rva<virtual_address+max(virtual_size,raw_size):directory=raw_pointer+debug_rva-virtual_address
                if directory is None or debug_size%28:raise ValueError('Invalid native debug directory')
                for i in range(0,debug_size,28):
                    record_type=struct.unpack_from('<I',data,directory+i+12)[0]
                    if record_type!=13:raise ValueError('PDB/CodeView or unknown debug record: '+relative)
        values[relative]=hashlib.sha256(data).hexdigest()
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deny-file',type=Path,help='Private local JSON array; never added to the release')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    deny=json.loads(args.deny_file.read_text(encoding='utf-8')) if args.deny_file else []
    values=audit(deny)
    report={'passed':True,'files_checked':len(values),'vendor_binaries_included':False,
            'user_projects_included':False,'runtime_logs_included':False,'native_pdb_records':0,
            'allowed_native_metadata':'MSVC POGO section layout only; no CodeView/PDB records',
            'private_denylist_checked':bool(deny),'method':'Explicit allowlist; credential and home-path patterns; private denylist; UTF-8/UTF-16/GB18030 byte checks; PE32 debug-directory checks'}
    (ROOT/'privacy-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    values['privacy-audit.json']=hashlib.sha256((ROOT/'privacy-audit.json').read_bytes()).hexdigest()
    (ROOT/'release-files.json').write_text(json.dumps({'schema':1,'version':'0.1.0','files':values},sort_keys=True,indent=2)+'\n',encoding='utf-8')
    if args.out.exists():raise ValueError('Refusing to overwrite release archive')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for relative in sorted([*values,'release-files.json']):
            info=zipfile.ZipInfo('systemview5-automation/'+relative,date_time=(2026,10,22,0,0,0))
            info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,(ROOT/relative).read_bytes())
    digest=hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(args.out.suffix+'.sha256').write_text(digest+'  '+args.out.name+'\n',encoding='ascii')
    print(json.dumps({'passed':True,'files':len(values)+1,'archive':args.out.name,'bytes':args.out.stat().st_size,'sha256':digest}))


if __name__=='__main__':main()
