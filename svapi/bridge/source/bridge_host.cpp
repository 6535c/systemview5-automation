#include <windows.h>
#include <stdio.h>
#include <wincrypt.h>
static bool verifiedBinary(const WCHAR* path){
 const BYTE expected[32]={0x82,0xf1,0xa0,0xf8,0x23,0x45,0x0d,0xcf,0x94,0x39,0x37,0x0c,0x3e,0x7c,0x60,0x1e,0x99,0xda,0x05,0xd5,0xab,0xa0,0x08,0xab,0x96,0x38,0x5f,0x41,0x39,0x8f,0x00,0x1f};
 HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,0,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,0);
 if(file==INVALID_HANDLE_VALUE)return false;
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;bool valid=false;
 if(CryptAcquireContextW(&provider,0,0,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)&&CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)){
  BYTE block[65536],digest[32];DWORD count=0,size=32;BOOL ok=TRUE;
  while((ok=ReadFile(file,block,sizeof(block),&count,0))&&count){if(!CryptHashData(hash,block,count,0)){ok=FALSE;break;}}
  valid=ok&&CryptGetHashParam(hash,HP_HASHVAL,digest,&size,0)&&size==32&&!memcmp(digest,expected,32);
 }
 if(hash)CryptDestroyHash(hash);if(provider)CryptReleaseContext(provider,0);CloseHandle(file);return valid;
}
int wmain(int argc,wchar_t**argv){
 if(argc!=6||wcscmp(argv[5],L"server"))return 2;HWND hwnd=(HWND)wcstoul(argv[1],0,10);DWORD pid=0;DWORD tid=GetWindowThreadProcessId(hwnd,&pid);
 DWORD expected=wcstoul(argv[2],0,10);ULONGLONG creation=_wcstoui64(argv[3],0,10);
 if(!tid||pid==GetCurrentProcessId()||pid!=expected)return 3;
 HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!process)return 8;
 WCHAR image[MAX_PATH];DWORD length=MAX_PATH;FILETIME times[4];
 BOOL identity=QueryFullProcessImageNameW(process,0,image,&length)&&GetProcessTimes(process,&times[0],&times[1],&times[2],&times[3]);
 ULARGE_INTEGER created;created.LowPart=times[0].dwLowDateTime;created.HighPart=times[0].dwHighDateTime;CloseHandle(process);
 WCHAR expectedImage[32768];DWORD expectedLength=GetFullPathNameW(argv[4],32768,expectedImage,0);
 if(!identity||created.QuadPart!=creation||!expectedLength||expectedLength>=32768||_wcsicmp(image,expectedImage)||!verifiedBinary(image))return 9;
 WCHAR cls[256];GetClassNameW(hwnd,cls,256);if(wcscmp(cls,L"ThunderRT6FormDC"))return 4;
 WCHAR path[MAX_PATH];GetModuleFileNameW(0,path,MAX_PATH);WCHAR* slash=wcsrchr(path,L'\\');wcscpy_s(slash+1,MAX_PATH-(slash+1-path),L"vbbridge.dll");
 HMODULE dll=LoadLibraryW(path);if(!dll){printf("LoadLibrary error %lu\n",GetLastError());return 5;}
 auto hookproc=(HOOKPROC)GetProcAddress(dll,"_HookProc@12");
 HHOOK hook=SetWindowsHookExW(WH_CALLWNDPROC,hookproc,dll,tid);
 if(!hook){printf("hook error %lu\n",GetLastError());return 6;}
 {
  DWORD_PTR result=0;SendMessageTimeoutW(hwnd,WM_APP+347,0x53564235,0,SMTO_ABORTIFHUNG,5000,&result);
  printf("ready pid=%lu hwnd=%lu\n",pid,(DWORD)hwnd);fflush(stdout);
  WCHAR eventName[100];swprintf_s(eventName,L"Local\\SystemViewBridgeStop-%lu",pid);HANDLE stop=CreateEventW(0,TRUE,FALSE,eventName);
  while(IsWindow(hwnd)&&WaitForSingleObject(stop,50)==WAIT_TIMEOUT){MSG m;while(PeekMessageW(&m,0,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
  CloseHandle(stop);UnhookWindowsHookEx(hook);FreeLibrary(dll);return 0;
 }
}
