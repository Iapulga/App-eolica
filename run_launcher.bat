@echo off
REM Lanza la CARCASA DE ESCRITORIO (ventana Discord/Steam con QtWebEngine/Chromium)
REM en modo DEBUG (desde codigo, no el .exe). Es el launcher propio de SMA 2.0:
REM ventana sin marco + barra de titulo custom + zoom + tema + splash.
REM El servidor Streamlit arranca como subproceso hijo en 127.0.0.1:8501.
setlocal
set PY=C:\Users\rudis\AppData\Local\Python\bin\python.exe
if not exist "%PY%" (
  echo [ERROR] No se encontro: %PY%
  echo Instala Python 3.14 desde https://www.python.org/ o ajusta PY en este .bat
  pause
  exit /b 1
)
cd /d "%~dp0"
"%PY%" desktop_shell.py
pause
