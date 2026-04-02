@echo off
echo ================================================
echo   LSPDFR AI Dispatch — Build Release Package
echo ================================================
echo.

cd /d "%~dp0\.."

REM --- Build the desktop app EXE ---
echo [1/3] Building DispatchRadio.exe...
pip install -r backend\requirements.txt -r dispatch_radio\requirements.txt pyinstaller 2>nul
pyinstaller --onefile --name DispatchRadio --console --add-data "backend;backend" --add-data "dispatch_radio;dispatch_radio" --add-data "cad\src;cad" launcher.py
if errorlevel 1 (
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)
echo    Done.
echo.

REM --- Build the plugin DLL ---
echo [2/3] Building LSPDFRDispatch.dll...
if not exist "plugin\lib\RagePluginHook.dll" (
    echo    SKIPPING plugin build — lib DLLs not found.
    echo    Copy RagePluginHook.dll and LSPD First Response.dll to plugin\lib\
    echo    Then re-run this script.
) else (
    cd plugin
    dotnet build -c Release
    cd ..
    echo    Done.
)
echo.

REM --- Assemble the release zip ---
echo [3/3] Assembling release package...

if exist "release" rmdir /s /q "release"
mkdir release
mkdir release\LSPDFRDispatch
mkdir release\LSPDFRDispatch\DispatchRadio
mkdir release\LSPDFRDispatch\Plugins

REM Desktop app
copy dist\DispatchRadio.exe release\LSPDFRDispatch\DispatchRadio\
copy config.ini release\LSPDFRDispatch\DispatchRadio\ 2>nul

REM Create default config if it doesn't exist
if not exist "release\LSPDFRDispatch\DispatchRadio\config.ini" (
    echo [General] > release\LSPDFRDispatch\DispatchRadio\config.ini
    echo OpenAIApiKey= >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo ApiKey=dispatch-secret >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo OfficerCallsign=1-Adam-12 >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo Port=8000 >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo. >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo [Audio] >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo WakeThreshold=2000 >> release\LSPDFRDispatch\DispatchRadio\config.ini
    echo SilenceTimeout=2.0 >> release\LSPDFRDispatch\DispatchRadio\config.ini
)

REM Plugin files
if exist "plugin\bin\Release\net48\LSPDFRDispatch.dll" (
    copy plugin\bin\Release\net48\LSPDFRDispatch.dll release\LSPDFRDispatch\Plugins\
    copy plugin\bin\Release\net48\Newtonsoft.Json.dll release\LSPDFRDispatch\Plugins\
)
copy plugin\LSPDFRDispatch.ini release\LSPDFRDispatch\Plugins\

REM Install instructions
(
echo LSPDFR AI Dispatch — Installation
echo ==================================
echo.
echo 1. PLUGIN: Copy everything from the Plugins\ folder into your
echo    GTA V\Plugins\ folder.
echo.
echo 2. DESKTOP APP: Put the DispatchRadio\ folder anywhere you like.
echo    Edit DispatchRadio\config.ini and add your OpenAI API key.
echo    Then run DispatchRadio.exe.
echo.
echo 3. CAD: Once DispatchRadio.exe is running, open your browser to:
echo    http://localhost:8000
echo.
echo 4. PLAY: Launch GTA V via RagePluginHook, go on duty in LSPDFR,
echo    and say "dispatch" to talk to your AI dispatcher!
echo.
echo CONFIGURATION:
echo   Edit DispatchRadio\config.ini to change:
echo   - OpenAIApiKey: Your OpenAI API key (required for voice)
echo   - OfficerCallsign: Your unit callsign
echo   - Port: Backend port (default 8000)
echo.
echo   Edit Plugins\LSPDFRDispatch.ini to change:
echo   - BackendUrl: Must match the desktop app's port
echo   - ApiKey: Must match the desktop app's ApiKey
) > release\LSPDFRDispatch\INSTALL.txt

REM Zip it
echo.
echo Release package assembled at: release\LSPDFRDispatch\
echo.
echo To distribute: zip the release\LSPDFRDispatch folder.
echo Users extract it and follow INSTALL.txt.
echo.
pause
