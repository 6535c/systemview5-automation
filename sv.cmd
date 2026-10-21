@echo off
setlocal
set "PYTHONUTF8=1"
if defined SV5_PYTHON goto custom
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto python
echo Python 3.10 or newer is required. Install Python or set SV5_PYTHON.
exit /b 1
:custom
"%SV5_PYTHON%" "%~dp0sv.py" %*
exit /b %errorlevel%
:launcher
py -3 "%~dp0sv.py" %*
exit /b %errorlevel%
:python
python "%~dp0sv.py" %*
exit /b %errorlevel%
