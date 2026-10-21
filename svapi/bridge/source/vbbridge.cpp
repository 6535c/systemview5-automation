#include <windows.h>
#include <oleauto.h>
#include <stdio.h>
#include <float.h>
#include <intrin.h>
static HMODULE module;
static DWORD rotToken;
static void unregisterForms(){
 if(!rotToken)return;
 IRunningObjectTable* rot=0;
 if(SUCCEEDED(GetRunningObjectTable(0,&rot))){rot->Revoke(rotToken);rot->Release();rotToken=0;}
}
static void siblingPath(WCHAR* path,const WCHAR* name){GetModuleFileNameW(module,path,MAX_PATH);WCHAR* p=wcsrchr(path,L'\\');wcscpy_s(p+1,MAX_PATH-(p+1-path),name);}
static HRESULT get(IDispatch* obj,const wchar_t* name,VARIANT* result,VARIANT* args=0,UINT count=0){
 DISPID id;LPOLESTR n=(LPOLESTR)name;HRESULT hr=obj->GetIDsOfNames(IID_NULL,&n,1,0,&id);if(FAILED(hr))return hr;
 DISPPARAMS p={args,0,count,0};return obj->Invoke(id,IID_NULL,0,DISPATCH_PROPERTYGET,&p,result,0,0);
}
static HRESULT method(IDispatch* obj,const wchar_t* name,VARIANT* args,UINT count){
 DISPID id;LPOLESTR n=(LPOLESTR)name;HRESULT hr=obj->GetIDsOfNames(IID_NULL,&n,1,0,&id);if(FAILED(hr))return hr;
 DISPPARAMS p={args,0,count,0};VARIANT result;VariantInit(&result);hr=obj->Invoke(id,IID_NULL,0,DISPATCH_METHOD,&p,&result,0,0);VariantClear(&result);return hr;
}
static void inspectForms(IUnknown* object,FILE* f){
 IDispatch* disp=0;HRESULT hr=object->QueryInterface(IID_IDispatch,(void**)&disp);fprintf(f,"QI IDispatch %08lx ptr=%p\n",hr,disp);if(!disp)return;
 ITypeInfo* ti=0;BSTR name=0;if(SUCCEEDED(disp->GetTypeInfo(0,0,&ti))){ti->GetDocumentation(MEMBERID_NIL,&name,0,0,0);fprintf(f,"type=%ls\n",name?name:L"?");SysFreeString(name);ti->Release();}
 VARIANT value;VariantInit(&value);hr=get(disp,L"Forms",&value);fprintf(f,"Forms %08lx vt=%d ptr=%p\n",hr,value.vt,value.pdispVal);
 IDispatch* forms=(SUCCEEDED(hr)&&value.vt==VT_DISPATCH)?value.pdispVal:disp;
 VARIANT count;VariantInit(&count);hr=get(forms,L"Count",&count);fprintf(f,"Count %08lx vt=%d n=%ld\n",hr,count.vt,count.lVal);
 if(SUCCEEDED(hr))for(int i=0;i<count.lVal && i<256;i++){
  VARIANT index;VariantInit(&index);index.vt=VT_I4;index.lVal=i;VARIANT form;VariantInit(&form);hr=get(forms,L"Item",&form,&index,1);
  fprintf(f,"Item %d %08lx vt=%d ptr=%p\n",i,hr,form.vt,form.pdispVal);
  if(SUCCEEDED(hr)&&form.vt==VT_DISPATCH){VARIANT fn;VariantInit(&fn);HRESULT h=get(form.pdispVal,L"Name",&fn);fprintf(f," name %08lx =%ls\n",h,fn.vt==VT_BSTR?fn.bstrVal:L"?");VariantClear(&fn);}
  VariantClear(&form);
 }
 VariantClear(&count);VariantClear(&value);disp->Release();
}
static HRESULT registerForms() {
    // Address recovered from this executable's VB ProjectData ExternalTable.
    IUnknown* global = *(IUnknown**)0x012807B0;
    if (!global) return E_POINTER;
    IDispatch* forms=0;
    typedef HRESULT(__stdcall* GetForms)(IUnknown*,IDispatch**);
    HRESULT access=((GetForms)(*(void***)global)[10])(global,&forms);
    if(FAILED(access)||!forms)return access;
    IRunningObjectTable* rot=0; IMoniker* mon=0;
    HRESULT hr=GetRunningObjectTable(0,&rot);
    WCHAR path[MAX_PATH];GetModuleFileNameW(module,path,MAX_PATH);
    WCHAR* slash=wcsrchr(path,L'\\');if(!slash)return E_FAIL;
    swprintf_s(slash+1,MAX_PATH-(slash+1-path),L"sv-%lu.forms",GetCurrentProcessId());
    if(SUCCEEDED(hr))hr=CreateFileMoniker(path,&mon);
    if(SUCCEEDED(hr))hr=rot->Register(ROTFLAGS_REGISTRATIONKEEPSALIVE,forms,mon,&rotToken);
    if(mon)mon->Release();if(rot)rot->Release();
    slash=wcsrchr(path,L'\\');wcscpy_s(slash+1,MAX_PATH-(slash+1-path),L"bridge-register.txt");
    FILE* f=0;_wfopen_s(&f,path,L"w");if(f){fprintf(f,"pid=%lu hr=0x%08lx token=%lu forms=%p\n",GetCurrentProcessId(),hr,rotToken,forms);inspectForms(forms,f);fclose(f);}
    forms->Release();return hr;
}
static void executeAction(DWORD request){
 WCHAR path[MAX_PATH],file[100];swprintf_s(file,L"request-%lu-%lu.txt",GetCurrentProcessId(),request);siblingPath(path,file);FILE* f=0;_wfopen_s(&f,path,L"r");if(!f)return;
 char op[80]={0};int index=0;float x=0,y=0;fscanf_s(f,"%79s %d %f %f",op,(unsigned)_countof(op),&index,&x,&y);fclose(f);
 HRESULT hr=E_INVALIDARG;
 if(!strcmp(op,"control.focus")){
  HWND input=(HWND)index;DWORD pid=0;GetWindowThreadProcessId(input,&pid);
  if(pid==GetCurrentProcessId()&&IsWindowVisible(input)&&IsWindowEnabled(input)){SetFocus(input);hr=GetFocus()==input?S_OK:E_FAIL;}
  swprintf_s(file,L"response-%lu-%lu.json",GetCurrentProcessId(),request);siblingPath(path,file);_wfopen_s(&f,path,L"w");if(f){fprintf(f,"{\"operation\":\"control.focus\",\"index\":%d,\"hresult\":%ld}\n",index,hr);fclose(f);}return;
 }
 IUnknown* global=*(IUnknown**)0x012807B0;IDispatch* forms=0;
 typedef HRESULT(__stdcall* GetForms)(IUnknown*,IDispatch**);
 if(global)hr=((GetForms)(*(void***)global)[10])(global,&forms);
 if(forms){
  hr=E_INVALIDARG;
  VARIANT count;VariantInit(&count);get(forms,L"Count",&count);
  for(int i=0;i<count.lVal;i++){
   VARIANT arg;VariantInit(&arg);arg.vt=VT_I4;arg.lVal=i;VARIANT form;VariantInit(&form);
   if(SUCCEEDED(get(forms,L"Item",&form,&arg,1))&&form.vt==VT_DISPATCH){
    VARIANT name;VariantInit(&name);get(form.pdispVal,L"Name",&name);
    VARIANT visible;VariantInit(&visible);get(form.pdispVal,L"Visible",&visible);
    if(visible.vt==VT_BOOL&&visible.boolVal==VARIANT_FALSE){VariantClear(&visible);VariantClear(&name);VariantClear(&form);continue;}
    VariantClear(&visible);
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"TimeForm")&&!strcmp(op,"time.validate")){
     DWORD address=0;
     switch(index){case 18:address=0xCA64A2;break;case 20:address=0xCAB80B;break;case 22:address=0xCA821C;break;case 24:address=0xCAF5C9;break;case 26:address=0xCAE695;break;case 28:address=0xCAD8D5;break;}
     if(address){typedef HRESULT(__stdcall* Validate)(IDispatch*,short*);short cancel=0;hr=((Validate)address)(form.pdispVal,&cancel);if(cancel)hr=E_INVALIDARG;}
    }
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"CalcForm")&&index>=0&&index<=128){
     typedef HRESULT(__stdcall* Event)(IDispatch*,short*);short choice=(short)index;
     if(!strcmp(op,"calculator.select")&&index<=1)hr=((Event)0xF41B04)(form.pdispVal,&choice);
     if(!strcmp(op,"calculator.apply")&&index<=1)hr=((Event)0xF27734)(form.pdispVal,&choice);
     if(!strcmp(op,"calculator.operation"))hr=((Event)0xF34D51)(form.pdispVal,&choice);
    }
    const WCHAR* selectorForm=0;DWORD selectorAddress=0;
    if(!strcmp(op,"source.select")&&index>=0&&index<=16){selectorForm=L"SourceWindow";selectorAddress=0xCA2932;}
    if(!strcmp(op,"sink.select")&&index>=0&&index<=16){selectorForm=L"SinkForm";selectorAddress=0xCB5523;}
    if(!strcmp(op,"operator.select")&&index>=0&&index<=256){selectorForm=L"LibForm";selectorAddress=0xCD2DE6;}
    if(!strcmp(op,"function.select")&&index>=0&&index<=256){selectorForm=L"FctForm";selectorAddress=0xCC0160;}
    if(!strcmp(op,"logic.select")&&index>=0&&index<=256){selectorForm=L"LogicLibForm";selectorAddress=0xED762C;}
    if(name.vt==VT_BSTR&&selectorForm&&!wcscmp(name.bstrVal,selectorForm)){
     typedef HRESULT(__stdcall* Select)(IDispatch*,short*);short choice=(short)index;
     hr=((Select)selectorAddress)(form.pdispVal,&choice);
    }
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"SystemDesign")&&index>=0&&index<=1023){
     typedef HRESULT(__stdcall* Select)(IDispatch*,short*);short choice=(short)index;
     if(!strcmp(op,"token.open"))hr=((Select)0xB2B3EB)(form.pdispVal,&choice);
     if(!strcmp(op,"token.click"))hr=((Select)0xB280DE)(form.pdispVal,&choice);
     if(!strcmp(op,"time.open"))hr=((Select)0xB9F89D)(form.pdispVal,&choice);
    }
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"SystemDesign")&&!strcmp(op,"toolbar.click")&&index>=1&&index<=29){
     VARIANT bar,buttons,button,idx;VariantInit(&bar);VariantInit(&buttons);VariantInit(&button);VariantInit(&idx);idx.vt=VT_I4;idx.lVal=index;
     hr=get(form.pdispVal,L"SysToolbar",&bar);
     if(SUCCEEDED(hr)&&bar.vt==VT_DISPATCH)hr=get(bar.pdispVal,L"Buttons",&buttons);
     if(SUCCEEDED(hr)&&buttons.vt==VT_DISPATCH)hr=get(buttons.pdispVal,L"Item",&button,&idx,1);
     if(SUCCEEDED(hr)&&button.vt==VT_DISPATCH){typedef HRESULT(__stdcall* Click)(IDispatch*,IDispatch*);hr=((Click)0xB991A2)(form.pdispVal,button.pdispVal);}
     VariantClear(&button);VariantClear(&buttons);VariantClear(&bar);
    }
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"MDI_Form")&&(!strcmp(op,"analysis.toolbar")||!strcmp(op,"analysis.calculator"))&&index>=1&&index<=21){
     bool calc=!strcmp(op,"analysis.calculator");VARIANT bar,buttons,button,idx;VariantInit(&bar);VariantInit(&buttons);VariantInit(&button);VariantInit(&idx);idx.vt=VT_I4;idx.lVal=index;
     hr=get(form.pdispVal,calc?L"ToolbarCalc":L"Toolbar",&bar);
     if(SUCCEEDED(hr)&&bar.vt==VT_DISPATCH)hr=get(bar.pdispVal,L"Buttons",&buttons);
     if(SUCCEEDED(hr)&&buttons.vt==VT_DISPATCH)hr=get(buttons.pdispVal,L"Item",&button,&idx,1);
     if(SUCCEEDED(hr)&&button.vt==VT_DISPATCH){typedef HRESULT(__stdcall* Click)(IDispatch*,IDispatch*);hr=((Click)(calc?0xFC3B70:0xFB1D48))(form.pdispVal,button.pdispVal);}
     VariantClear(&button);VariantClear(&buttons);VariantClear(&bar);
    }
    if(name.vt==VT_BSTR&&!wcscmp(name.bstrVal,L"SystemDesign")&&!strcmp(op,"grid.drop")&&index>=0&&index<=15&&x>=0&&x<=30000&&y>=0&&y<=18000){
     // Call the same five-argument token constructor used by the normal drop
     // handler. The engine allocates and initializes its own model state.
     // No process globals/object fields are written by this adapter.
     IUnknown* design=0;
     hr=form.pdispVal->QueryInterface(*(GUID*)0x004E2E0C,(void**)&design);
     if(SUCCEEDED(hr)&&design){
      short kind=(short)index,createNew=VARIANT_TRUE;
      typedef void(__stdcall* CreateToken)(IUnknown**,float*,float*,short*,short*);
      ((CreateToken)0x007B66F8)(&design,&x,&y,&kind,&createNew);
      design->Release();hr=S_OK;
     }
    }
    VariantClear(&name);
   }VariantClear(&form);
  }VariantClear(&count);forms->Release();
 }
 swprintf_s(file,L"response-%lu-%lu.json",GetCurrentProcessId(),request);siblingPath(path,file);_wfopen_s(&f,path,L"w");if(f){fprintf(f,"{\"operation\":\"%s\",\"index\":%d,\"hresult\":%ld}\n",op,index,hr);fclose(f);}
}
extern "C" __declspec(dllexport) LRESULT CALLBACK HookProc(int code,WPARAM wp,LPARAM lp){
    static DWORD lastRequest=0;
    if(code>=0){CWPSTRUCT* m=(CWPSTRUCT*)lp;if(m->wParam==0x53564235){
     // VB6 and the C runtime use different floating-point exception conventions.
     // Isolate the callback, including its native VB6 events, from the caller's
     // x87/SSE registers, exception flags, masks and precision settings.
     __declspec(align(16)) unsigned char fp[512];_fxsave(fp);_clearfp();_control87(_MCW_EM,_MCW_EM);
     if(m->message==WM_APP+347)registerForms();
     if(m->message==WM_APP+349)unregisterForms();
     if(m->message==WM_APP+348&&(DWORD)m->lParam!=lastRequest){lastRequest=(DWORD)m->lParam;executeAction(lastRequest);}
     _clearfp();_fxrstor(fp);
    }}
    return CallNextHookEx(0,code,wp,lp);
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH){module=instance;DisableThreadLibraryCalls(instance);}return TRUE;}
