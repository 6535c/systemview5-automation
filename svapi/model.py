"""Construct, connect and run real SystemView models through its native objects."""
from pathlib import Path
import json,time
from svctl import BridgeError
from .native import Native

LIBRARIES={'source':('SourceWindow','SystemView Source Library'),
 'operator':('LibForm','SystemView Operator Library'),
 'function':('FctForm','SystemView Function Library'),
 'sink':('SinkForm','Sink Definition'),
 'logic':('LogicLibForm','SystemView Logic Library')}

class Model:
 def __init__(self,session,initial_count=0):self.s=session;self.n=Native(session);self.log=[];self.analysis_request=None;self.count=initial_count
 def begin_button(self,dialog,hwnd):
  selector='@'+str(dialog)
  buttons=[c for c in self.n.controls(selector) if c['hWnd']==hwnd]
  if len(buttons)!=1:raise BridgeError('Cannot identify the native command button')
  button=buttons[0];args=[selector,'click',button['Name']]
  index=[button['Index']] if button['Index'] is not None else []
  return self.n.begin_com(*args,*index)
 def add(self,kind,x,y):
  before=self.tokens();self.n.action('grid.drop',kind,x*15,y*15);after=self.s.tokens()
  if len(after)!=len(before)+1:raise BridgeError('A drop did not add exactly one token')
  token=after[-1]['id'];self.count=len(after);self.log.append({'add':token,'reservoir':kind,'position':[x,y]});return token
 def tokens(self):
  # The native Finder has no dialog for an empty model.
  return self.s.tokens() if self.count else []
 def define(self,token,library,choice,params=None):
  form,title=LIBRARIES[library];d,r=self.n.open_token(token,title)
  if isinstance(choice,str):
   controls=self.n.controls(form)
   matches=[c['Index'] for c in controls if 'LabelArray' in c['Name'] and c['Caption'] and c['Caption'].strip().casefold()==choice.casefold()]
   if len(matches)!=1:raise BridgeError(f'Library choice {choice!r} matched {matches}')
   choice=matches[0]
  self.n.action(library+'.select',choice)
  feedback=[]
  parameter_button=self.s.control(d,text='Parameters')
  if params is not None or (library!='sink' and self.s.win.u.IsWindowEnabled(parameter_button)):
   # VB6 can ignore BM_CLICK when a library dialog has just been reused.
   # Use the exact visible form's CommandButton.Value. Its Click handler opens
   # a modal dialog, so keep that COM call alive until the dialog is confirmed.
   pending=self.begin_button(d,parameter_button)
   e=self.s.wait(lambda:self.s.dialog(predicate=lambda h:self.s.win.cls(h)=='ThunderRT6FormDC' and any(self.s.win.u.GetDlgCtrlID(c)==39 for c in self.s.win.children(h))),'token parameters')
   visible=[c for c in self.s.win.children(e) if self.s.win.u.IsWindowVisible(c)]
   feedback=[self.s.win.describe(c) for c in visible]
   for cid,value in (params or {}).items():
    field=self.s.control(e,cid=int(cid))
    if field not in visible or 'textbox' not in self.s.win.cls(field).casefold():
     raise BridgeError(f'Parameter {cid} is not a visible numeric field')
    self.s.set_text(field,value)
   confirmation=self.begin_button(e,self.s.control(e,cid=39))
   self.s.wait(lambda:not self.s.win.u.IsWindowVisible(e),'parameter close')
   self.n.finish_com(confirmation)
   self.n.finish_com(pending)
  confirmation=self.begin_button(d,self.s.control(d,text='OK'))
  self.s.wait(lambda:not self.s.win.u.IsWindowVisible(d),'library close')
  self.n.finish_com(confirmation);self.n.finish(r)
  self.log.append({'define':token,'library':library,'choice':choice,'params':params,'native_parameter_fields':feedback})
  return token
 def connect(self,source,target,port=None,out_port=None):
  self.n.com('SystemDesign','call','tool_Connect')
  selected=[]
  for token in [source,target]:
   response=self.n.begin('token.click',token);deadline=time.monotonic()+12
   while not response.exists():
    d=self.s.dialog(predicate=lambda h:self.s.win.cls(h)=='ThunderRT6FormDC' and h!=self.s.frame('design') and any('OptionButton' in self.s.win.cls(c) and self.s.win.u.IsWindowVisible(c) for c in self.s.win.children(h)))
    if d:
     options=[c for c in self.s.win.children(d) if 'OptionButton' in self.s.win.cls(c) and self.s.win.u.IsWindowVisible(c)]
     def port_name(control):
      label=self.s.win.text(control)
      return label.split(':',1)[1].strip() if ':' in label and label.split(':',1)[0].strip().isdigit() else label
     candidates=[c for c in options if any(choice is not None and self.s.win.normalize(port_name(c))==self.s.win.normalize(choice) for choice in [port,out_port])]
     if len(candidates)!=1:raise BridgeError(f'Port selection must match one choice: {[self.s.win.text(c) for c in options]}')
     radio=candidates[0];self.s.press(radio);self.s.wait(lambda:self.s.win.send(radio,0xF0)==1,'selected native port')
     selected.append({'dialog':self.s.win.text(d),'port':self.s.win.text(radio),'choices':[self.s.win.text(c) for c in options]})
     self.s.press(self.s.control(d,text='OK'));self.s.wait(lambda:not self.s.win.u.IsWindowVisible(d),'port dialog close')
    if time.monotonic()>deadline:raise BridgeError('Connection event did not return')
    time.sleep(.04)
   result=self.n.finish(response)
   if result['index']!=token:raise BridgeError('Wrong token acknowledgement')
  self.log.append({'connect':[source,target],'port':port,'output_port':out_port,'native_choices':selected})
 def timing(self,fs=10000,stop=.5,start=0):
  response=self.n.begin('toolbar.click',27);d=self.s.wait(lambda:self.s.dialog(title='System Time Specification'),'system time')
  for cid,value in [(28,start),(20,fs),(26,stop)]:
   self.s.set_text(self.s.control(d,cid=cid),value);self.n.action('time.validate',cid)
  result={str(cid):self.s.win.text(self.s.control(d,cid=cid)) for cid in [18,20,22,24,26,28]}
  if int(float(result['22']))!=round((stop-start)*fs)+1:raise BridgeError('Incorrect native sample count')
  self.s.press(self.s.control(d,cid=30));self.s.wait(lambda:not self.s.win.u.IsWindowVisible(d),'time close');self.n.finish(response)
  self.log.append({'timing':result});return result
 def run(self,count):
  self.n.action('toolbar.click',25)
  self.analysis_request=self.n.begin('toolbar.click',29)
  self.s.wait(lambda:len(self.s.plots())==count,'all expected real waveforms')
  return self.s.plots()
 def close_analysis(self):
  self.close_calculator()
  frame=self.s.frame('analysis');self.s.win.post(frame,0x10)
  self.s.wait(lambda:not self.s.win.u.IsWindow(frame) or not self.s.win.u.IsWindowVisible(frame),'analysis close')
  if self.analysis_request:self.n.finish(self.analysis_request);self.analysis_request=None
 def calculator(self):
  return next((h for h in self.s.win.children(self.s.frame('analysis'))
               if self.s.win.text(h)=='Sink Calculator' and self.s.win.u.IsWindowVisible(h)),None)
 def close_calculator(self):
  calc=self.calculator()
  if calc:
   self.s.win.post(calc,0x10)
   self.s.wait(lambda:not self.s.win.u.IsWindowVisible(calc),'calculator close')
 def spectrum(self,plot_name,output,image=True):
  """Use the actual Sink Calculator; export immediately because it reuses wN."""
  import re
  target=[p for p in self.s.plots() if p['text'].split(':',1)[0]==plot_name]
  if len(target)!=1:raise BridgeError(f'Unknown input plot: {plot_name}')
  match=re.fullmatch(r'w\d+: Sink (\d+)',target[0]['text'])
  if not match:raise BridgeError('Spectrum input must be an original sink waveform')
  sink=int(match[1])
  if not self.calculator():self.n.action('analysis.calculator',1)
  calc=self.s.wait(self.calculator,'sink calculator')
  self.n.com('CalcForm','tab',6)
  controls=self.n.controls('CalcForm')
  radio=next(c['hWnd'] for c in controls if c['Name']=='OprOption' and c['Index']==35)
  # VB6 option buttons can lose Value on repeated BM_CLICK. Set the native COM
  # property explicitly and verify both property and window-message readback.
  if self.n.com('CalcForm','value','OprOption','true',35) is not True:
   raise BridgeError('Native spectrum option Value was not retained')
  self.s.wait(lambda:self.s.win.send(radio,0xF0)==1,'native power spectrum selection')
  self.n.action('calculator.operation',35)
  tabs=self.n.com('CalcForm','tabs')
  if not any(t['index']==6 and t['selected'] for t in tabs):raise BridgeError('Spectrum tab was not selected')
  listing=next(c['hWnd'] for c in controls if c['Name']=='SinkListBox' and c['Index']==0)
  rows=self.s.win.describe(listing)['items']
  found=[i for i,row in enumerate(rows) if row.split(':',1)[0].strip()==plot_name]
  if len(found)!=1:raise BridgeError(f'Calculator input list did not contain exactly one {plot_name}: {rows}')
  index=found[0]
  self.s.win.send(listing,0x185,0,-1);self.s.win.send(listing,0x185,1,index);self.s.win.send(listing,0x19e,index)
  if self.s.win.send(listing,0x187,index)!=1:raise BridgeError('Calculator input selection failed')
  self.n.action('calculator.select',0);self.n.action('calculator.apply',1)
  expected=f'Power Spectrum of Sink {sink} (dBm 1 ohm) Mixed Radix'
  plot=self.s.wait(lambda:next((p for p in self.s.plots() if p['text'].split(': ',1)[-1]==expected),None),'computed native power spectrum')
  name=plot['text'].split(':',1)[0];output=Path(output)
  result={'source':target[0]['text'],'data':self.s.export(name,output)}
  if image:result['image']=self.s.export_image(name,output.with_suffix('.wmf'))
  self.log.append({'spectrum':result})
  return result
 def save_log(self,path):Path(path).write_text(json.dumps(self.log,ensure_ascii=False,indent=2),encoding='utf-8')
 def select_calculator_input(self,plot_name,index=0):
  controls=self.n.controls('CalcForm')
  listing=next(c['hWnd'] for c in controls if c['Name']=='SinkListBox' and c['Index']==index)
  rows=self.s.win.describe(listing)['items']
  self.s.win.send(listing,0x185,0,-1)
  if plot_name is not None:
   found=[i for i,row in enumerate(rows) if row.split(':',1)[0].strip()==plot_name]
   if len(found)!=1:raise BridgeError(f'Unknown calculator input {plot_name}: {rows}')
   row=found[0];self.s.win.send(listing,0x185,1,row);self.s.win.send(listing,0x19e,row)
   if self.s.win.send(listing,0x187,row)!=1:raise BridgeError('Native calculator selection was not retained')
  self.n.action('calculator.select',index)
 def complex_fft(self,plot_name,output):
  """Native two-sided linear |FFT|/Fs, matching the lab's Cx FFT: Mag view."""
  import re
  targets=[p for p in self.s.plots() if p['text'].split(':',1)[0]==plot_name]
  if len(targets)!=1:raise BridgeError('Expected one FFT input waveform')
  match=re.fullmatch(r'w\d+: Sink (\d+)',targets[0]['text'])
  if not match:raise BridgeError('Complex FFT requires an original sink waveform')
  if not self.calculator():self.n.action('analysis.calculator',1)
  self.s.wait(self.calculator,'calculator');self.n.com('CalcForm','tab',5)
  self.n.com('CalcForm','value','OprOption','true',23);self.n.action('calculator.operation',23)
  controls=self.n.controls('CalcForm')
  no_padding=next(c['hWnd'] for c in controls if c['Name']=='calcCheck' and c['Index']==12)
  if self.s.win.send(no_padding,0xF0)!=1:
   self.s.press(no_padding);self.s.wait(lambda:self.s.win.send(no_padding,0xF0)==1,'FFT mixed radix')
  self.select_calculator_input(plot_name,0);self.select_calculator_input(None,1)
  listing=next(c['hWnd'] for c in controls if c['Name']=='OprListBox' and c['Index']==1)
  rows=self.s.win.describe(listing)['items'];index=rows.index('Magnitude')
  self.s.win.send(listing,0x185,0,-1);self.s.win.send(listing,0x185,1,index);self.s.win.send(listing,0x19e,index)
  self.s.win.send(self.s.win.u.GetParent(listing),0x111,(1<<16)|(self.s.win.u.GetDlgCtrlID(listing)&0xffff),listing)
  if self.s.win.send(listing,0x187,index)!=1:raise BridgeError('Magnitude output selection failed')
  response=self.n.begin('calculator.apply',1)
  def completed():
   if response.exists() and response.stat().st_size:return True
   dialog=self.s.dialog('SystemView Sink Calculator')
   if dialog:
    text=[self.s.win.text(c) for c in self.s.win.children(dialog)]
    if 'The imaginary FFT input is zero.  Is this correct?' in text:
     self.s.press(self.s.control(dialog,cid=6)) # explicit zero imaginary input
   return False
  self.s.wait(completed,'native complex FFT with zero imaginary input');self.n.finish(response)
  expected=f'Cx FFT: Mag Sink {int(match[1])} + j0 Mixed Radix'
  plot=self.s.wait(lambda:next((p for p in self.s.plots() if p['text'].split(': ',1)[-1]==expected),None),'native two-sided magnitude')
  name=plot['text'].split(':',1)[0]
  result={'plot':name,'source':targets[0]['text'],'data':self.s.export(name,output)}
  self.log.append({'complex_fft':result});return result
 def scale_view(self,plot_name,xlim,ylim):
  if not self.calculator():self.n.action('analysis.calculator',1)
  self.s.wait(self.calculator,'calculator');self.n.com('CalcForm','tab',8)
  self.n.com('CalcForm','value','OprOption','true',2);self.n.action('calculator.operation',2)
  self.select_calculator_input(plot_name)
  for index,value in [(4,xlim[0]),(6,xlim[1]),(5,ylim[0]),(7,ylim[1])]:self.n.com('CalcForm','text','ParamText',value,index)
  self.n.action('calculator.apply',1)
  plot=self.s.wait(lambda:next((p for p in self.s.plots() if p['text'].split(': ',1)[-1]=='Max-Min Scaled '+plot_name),None),'native scaled view')
  result={'plot':plot['text'].split(':',1)[0],'xlim':xlim,'ylim':ylim}
  self.log.append({'scale_view':result});return result
 def color_exports(self,enabled):
  self.close_calculator();self.s.menu('analysis','Preferences/Options')
  dialog=self.s.wait(lambda:self.s.dialog('SystemView Analysis Window'),'analysis options')
  control=self.s.control(dialog,cid=40);before=self.s.win.send(control,0xF0)==1
  if before!=bool(enabled):
   self.s.press(control);self.s.wait(lambda:(self.s.win.send(control,0xF0)==1)==bool(enabled),'native print/copy color option')
  self.s.press(self.s.control(dialog,cid=55));self.s.wait(lambda:not self.s.win.u.IsWindowVisible(dialog),'analysis options close')
  return before
