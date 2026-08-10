@echo off
REM Empaqueta spy_direction.py en un .exe autonomo (doble clic).
REM Requiere: pip install pyinstaller ib_insync
cd /d "%~dp0"
pip install pyinstaller ib_insync pandas tzdata
pyinstaller --onefile --windowed --name spy_direction --collect-all tzdata spy_direction.py
echo.
echo Listo. El ejecutable quedo en:  dist\spy_direction.exe
pause
