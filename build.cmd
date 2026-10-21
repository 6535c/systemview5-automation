@echo off
setlocal
if defined VSCMD_ARG_TGT_ARCH goto ready
set "SV5_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%SV5_VSWHERE%" goto missing
for /f "usebackq tokens=*" %%i in (`"%SV5_VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "SV5_VS=%%i"
if not defined SV5_VS goto missing
call "%SV5_VS%\VC\Auxiliary\Build\vcvars32.bat" >nul
if errorlevel 1 exit /b %errorlevel%
:ready
if /i not "%VSCMD_ARG_TGT_ARCH%"=="x86" (
  echo Use an x86 Developer Command Prompt.
  exit /b 1
)
pushd "%~dp0"
if not exist bin\win32 mkdir bin\win32
if not exist .build mkdir .build
cl /nologo /EHsc /O2 /MT /arch:SSE2 /LD /Fo.build\vbbridge.obj svapi\bridge\source\vbbridge.cpp /link /DEBUG:NONE ole32.lib oleaut32.lib user32.lib /OUT:bin\win32\vbbridge.dll /IMPLIB:.build\vbbridge.lib
if errorlevel 1 goto failed
cl /nologo /EHsc /O2 /MT /Fo.build\bridge_host.obj svapi\bridge\source\bridge_host.cpp /link /DEBUG:NONE user32.lib advapi32.lib /OUT:bin\win32\bridge_host.exe
if errorlevel 1 goto failed
"%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe" /nologo /debug- /optimize+ /platform:x86 /reference:System.Web.Extensions.dll /out:bin\win32\SvCom.exe svapi\bridge\source\SvCom.cs
if errorlevel 1 goto failed
call sv.cmd version >nul
if errorlevel 1 goto failed
if defined SV5_PYTHON (
  "%SV5_PYTHON%" tools\make_manifest.py
) else (
  py -3 tools\make_manifest.py
)
if errorlevel 1 goto failed
popd
exit /b 0
:failed
set "SV5_BUILD_ERROR=%errorlevel%"
popd
exit /b %SV5_BUILD_ERROR%
:missing
echo Install Visual Studio Build Tools with the Desktop development with C++ workload.
exit /b 1
