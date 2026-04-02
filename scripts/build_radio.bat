@echo off
echo ========================================
echo  Building LSPDFR Dispatch Radio EXE
echo ========================================

cd /d "%~dp0\.."

REM Install dependencies
pip install -r dispatch_radio\requirements.txt
pip install pyinstaller

REM Build the executable
pyinstaller --onefile --name DispatchRadio --console dispatch_radio\main.py

echo.
echo Build complete! EXE is at: dist\DispatchRadio.exe
echo.
pause
