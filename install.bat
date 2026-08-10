@echo off
REM ============================================================
REM  Instalador de un clic - SPY Direction (IBKR)
REM  Deja todo listo en una maquina nueva:
REM   1) verifica Python (lo instala con winget si falta)
REM   2) instala dependencias (ib_insync)
REM   3) construye el ejecutable dist\spy_direction.exe
REM ============================================================
setlocal
cd /d "%~dp0"
echo ============================================
echo   Instalando SPY Direction (IBKR)
echo ============================================
echo.

REM --- 1) Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [1/3] Python no encontrado. Intentando instalar con winget...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    echo   Cierra y vuelve a abrir esta ventana si Python no queda en PATH.
) else (
    echo [1/3] Python encontrado:
    python --version
)
echo.

REM --- 2) Dependencias ---
echo [2/3] Instalando dependencias (ib_insync, pyinstaller)...
python -m pip install --upgrade pip
python -m pip install ib_insync pandas tzdata pyinstaller
echo.

REM --- 3) Ejecutable ---
echo [3/3] Construyendo el ejecutable...
python -m PyInstaller --onefile --windowed --name spy_direction --collect-all tzdata spy_direction.py
echo.
echo ============================================
echo   LISTO
echo   Ejecutable: dist\spy_direction.exe
echo.
echo   Antes de usarlo: abre IB Gateway, loguea (paper) y
echo   habilita la API (Socket port 4002, Trusted IP 127.0.0.1).
echo ============================================
pause
endlocal
