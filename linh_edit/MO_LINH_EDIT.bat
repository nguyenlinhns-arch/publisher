@echo off
chcp 65001 >nul
pushd "%~dp0\.."
if exist "LinhEdit.exe" (
  start "" "LinhEdit.exe"
  exit /b 0
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m linh_edit
  set CODE=%errorlevel%
  popd
  exit /b %CODE%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python -m linh_edit
  set CODE=%errorlevel%
  popd
  exit /b %CODE%
)
echo Khong tim thay Python hoac LinhEdit.exe.
pause
popd
exit /b 1
