@echo off
REM ============================================================
REM  build.bat - Compila Alfa App a .exe
REM  Uso: doble-click  o  ejecutar 'build' en terminal
REM ============================================================

cd /d "%~dp0"

echo.
echo ================================================
echo   Compilando Alfa App a .exe
echo ================================================
echo.

REM Detecta python disponible (py launcher o python)
where py >nul 2>nul
if %errorlevel%==0 (
    py build_exe.py
) else (
    python build_exe.py
)

if errorlevel 1 (
    echo.
    echo *** Error en compilacion ***
    pause
    exit /b 1
)

echo.
echo Presiona cualquier tecla para salir...
pause >nul
