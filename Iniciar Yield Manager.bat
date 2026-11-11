@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0yield_manager.pyw"
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0yield_manager.pyw"
  exit /b 0
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe" (
  start "" "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe" "%~dp0yield_manager.pyw"
  exit /b 0
)
echo No se encontro Python con Tcl/Tk.
echo Instala Python 3.10 o posterior desde python.org y vuelve a iniciar la aplicacion.
pause
