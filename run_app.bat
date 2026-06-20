@echo off
REM Arranca SMA 2.0 (carcasa de escritorio PySide6/QtWebEngine) con el Python 3.14
REM que tiene streamlit instalado.
REM (El `python` del PATH apunta al venv Hermes 3.11 sin streamlit.)
setlocal
set PY=C:\Users\rudis\AppData\Local\Python\bin\python.exe
if not exist "%PY%" (
  echo [ERROR] No se encontro: %PY%
  echo Instala Python 3.14 desde https://www.python.org/ o ajusta PY en este .bat
  pause
  exit /b 1
)
cd /d "%~dp0"
"%PY%" launcher.py
pause
