"""Generate hashes for the project's own, locally built native helpers."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]/'bin'/'win32'
names=['bridge_host.exe','vbbridge.dll','SvCom.exe']
values={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
(root/'manifest.json').write_text(json.dumps(values,sort_keys=True,indent=2)+'\n',encoding='utf-8')
print('Native helper manifest generated')
