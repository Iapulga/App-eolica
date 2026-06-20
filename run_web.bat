@echo off
REM Arranca SMA 2.0 en MODO WEB (navegador) con el Python 3.14 que tiene streamlit.
setlocal
set PY=C:\Users\rudis\AppData\Local\Python\bin\python.exe
if not exist "%PY%" (
  echo [ERROR] No se encontro: %PY%
  pause
  exit /b 1
)
cd /d "%~dp0"
"%PY%" -m streamlit run Inicio.py
pause
