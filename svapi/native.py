"""Version-pinned, local-only SystemView native model interface."""
import hashlib,json,subprocess,time,ctypes as C,secrets
from ctypes import wintypes as W
from pathlib import Path
from svctl import BridgeError
from svsettings import ensure_helpers,ENGINE_SHA
ROOT=None
class Native:
 def __init__(self,session):
  global ROOT
  ROOT=ensure_helpers()
  self.s=session;self.pid=session.state['pid'];self.moniker=ROOT/f'sv-{self.pid}.forms'
  if hashlib.sha256(Path(session.state['exe']).read_bytes()).hexdigest()!=ENGINE_SHA:raise BridgeError('Native API requires verified SystemView Build046 binary')
  state=ROOT/f'server-{self.pid}.json';alive=False
  if state.exists():
   old=json.loads(state.read_text(encoding='utf-8'))
   try:alive=session.win.identity(old['pid'])==old
   except BridgeError:pass
  if not alive:
   startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
   with (ROOT/f'server-{self.pid}.log').open('w') as log:
    helper=subprocess.Popen([str(ROOT/'bridge_host.exe'),str(session.handle(session.frame('design'))),str(self.pid),str(session.state['created']),str(session.state['exe']),'server'],stdout=log,stderr=log,startupinfo=startup)
   session.wait(lambda:'ready' in (ROOT/f'server-{self.pid}.log').read_text(encoding='utf-8'),'native server start')
   state.write_text(json.dumps(session.win.identity(helper.pid)),encoding='utf-8')
 def begin(self,op,index=0,x=0,y=0):
  # Windows wall-clock timestamps can repeat within one clock tick. Never use
  # them as command IDs: a repeated ID would silently suppress a second edge.
  request=secrets.randbelow(2147483646)+1
  while (ROOT/f'request-{self.pid}-{request}.txt').exists():request=secrets.randbelow(2147483646)+1
  path=ROOT/f'request-{self.pid}-{request}.txt'
  path.write_text(f'{op} {int(index)} {float(x)} {float(y)}\n',encoding='ascii')
  response=ROOT/f'response-{self.pid}-{request}.json'
  try:self.s.win.send(self.s.handle(self.s.frame('design')),0x8000+348,0x53564235,request,timeout=250)
  except BridgeError as error:
   # Modal event handlers keep their stack alive in the persistent server while
   # the caller handles the real dialog through native controls.
   if '1460' not in str(error):raise
  return response
 def finish(self,response,timeout=12):
  self.s.wait(lambda:response.exists() and response.stat().st_size,'native operation return',timeout)
  result=json.loads(response.read_text(encoding='utf-8'))
  if result['hresult']<0:raise BridgeError(f'Native operation failed: {result}')
  return result
 def action(self,op,index=0,x=0,y=0):return self.finish(self.begin(op,index,x,y))
 def controls(self,form):return self.com(form)
 def stop(self):
  # Release the ROT's strong reference on the VB6 Forms collection on its UI
  # thread, before unloading the hook or asking the application to shut down.
  self.s.win.send(self.s.handle(self.s.frame('design')),0x8000+349,0x53564235,0)
  k=self.s.win.k;k.OpenEventW.argtypes=[W.DWORD,W.BOOL,W.LPCWSTR];k.OpenEventW.restype=W.HANDLE;k.SetEvent.argtypes=[W.HANDLE]
  event=k.OpenEventW(2,False,f'Local\\SystemViewBridgeStop-{self.pid}')
  if event:k.SetEvent(event);k.CloseHandle(event)
  time.sleep(.2);self.s.win.send(self.s.frame('design'),0);time.sleep(.2)
 def begin_com(self,*args):
  startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
  return subprocess.Popen([str(ROOT/'SvCom.exe'),str(self.moniker),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',startupinfo=startup)
 def finish_com(self,process,timeout=15):
  stdout,stderr=process.communicate(timeout=timeout)
  if process.returncode:raise BridgeError(stderr)
  return json.loads(stdout)
 def com(self,*args):return self.finish_com(self.begin_com(*args))
 def open_token(self,token,title):
  response=self.begin('token.open',token)
  dialog=self.s.wait(lambda:self.s.dialog(title=title),'token library')
  return dialog,response
