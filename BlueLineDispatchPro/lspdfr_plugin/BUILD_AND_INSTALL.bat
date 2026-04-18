@echo off
title BlueLineDispatch Plugin Builder
color 0A
echo.
echo  ================================================
echo   BlueLineDispatchPro -- SHVDN Script Builder
echo  ================================================
echo.

:: ── Find the C# compiler (built into Windows .NET) ──────────────────────────
set CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" (
    set CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe
)
if not exist "%CSC%" (
    echo [ERROR] Could not find csc.exe - .NET Framework 4 not installed.
    echo         Download it from: https://dotnet.microsoft.com/download/dotnet-framework
    pause & exit /b 1
)
echo  [OK] Compiler found: %CSC%

:: ── Find GTA 5 install ───────────────────────────────────────────────────────
set GTA_DIR=
for %%D in (
    "C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy"
    "C:\Program Files\Rockstar Games\Grand Theft Auto V"
    "C:\Program Files (x86)\Rockstar Games\Grand Theft Auto V Legacy"
    "C:\Program Files (x86)\Rockstar Games\Grand Theft Auto V"
    "C:\Games\Grand Theft Auto V"
    "D:\SteamLibrary\steamapps\common\Grand Theft Auto V"
    "C:\SteamLibrary\steamapps\common\Grand Theft Auto V"
) do (
    if exist "%%~D\GTA5.exe" set GTA_DIR=%%~D
)

if "%GTA_DIR%"=="" (
    echo.
    echo  [!] Could not auto-detect GTA 5. Enter the full path to your GTA 5 folder:
    echo      (the folder that contains GTA5.exe, no quotes needed)
    echo.
    set /p GTA_DIR="  Path: "
    :: Strip any quotes the user may have typed
    set GTA_DIR=%GTA_DIR:"=%
)

if not exist "%GTA_DIR%\GTA5.exe" (
    echo [ERROR] GTA5.exe not found at: %GTA_DIR%
    pause & exit /b 1
)
echo  [OK] GTA 5 found: %GTA_DIR%

:: ── Find ScriptHookVDotNet3.dll ──────────────────────────────────────────────
set SHVDN_DLL=
for %%F in (
    "%GTA_DIR%\ScriptHookVDotNet3.dll"
    "%~dp0ScriptHookVDotNet3.dll"
) do (
    if exist "%%~F" set SHVDN_DLL=%%~F
)

if "%SHVDN_DLL%"=="" (
    echo.
    echo  ============================================================
    echo   ScriptHookVDotNet3.dll NOT FOUND
    echo  ============================================================
    echo.
    echo   1. Download from: https://github.com/scripthookvdotnet/scripthookvdotnet/releases
    echo   2. Extract ScriptHookVDotNet3.dll and ScriptHookVDotNet3.ini
    echo      into your GTA V folder: %GTA_DIR%
    echo   3. Run this script again.
    echo.
    pause & exit /b 1
)
echo  [OK] SHVDN3: %SHVDN_DLL%

:: Cache SHVDN3.dll next to the script so the compiler can always reach it
:: (avoids "access denied" reading directly from Program Files)
if not "%SHVDN_DLL%"=="%~dp0ScriptHookVDotNet3.dll" (
    copy /Y "%SHVDN_DLL%" "%~dp0ScriptHookVDotNet3.dll" >nul 2>&1
)
set SHVDN_DLL=%~dp0ScriptHookVDotNet3.dll

:: Output folder: GTA\scripts\  (SHVDN loads scripts from here)
set SCRIPTS_DIR=%GTA_DIR%\scripts
if not exist "%SCRIPTS_DIR%" (
    mkdir "%SCRIPTS_DIR%" 2>nul
    if errorlevel 1 (
        echo  [!] Could not create scripts folder -- make sure you RIGHT-CLICKED
        echo      and chose "Run as Administrator".
        pause & exit /b 1
    )
)
set PLUGIN_OUT=%SCRIPTS_DIR%\BlueLinePlugin.dll

echo.
echo  Compiling BlueLinePlugin.cs as SHVDN script...
echo.

:: ── Compile ──────────────────────────────────────────────────────────────────
"%CSC%" ^
    /target:library ^
    /optimize+ ^
    /out:"%~dp0BlueLinePlugin.dll" ^
    /reference:"%SHVDN_DLL%" ^
    /reference:"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.dll" ^
    "%~dp0BlueLinePlugin.cs"

if errorlevel 1 (
    echo.
    echo [ERROR] Compilation failed. See errors above.
    pause & exit /b 1
)
echo.
echo  [OK] Compiled successfully.

:: ── Install ───────────────────────────────────────────────────────────────────
copy /Y "%~dp0BlueLinePlugin.dll" "%PLUGIN_OUT%" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy DLL to scripts folder. Try running as Administrator.
    pause & exit /b 1
)

echo  [OK] Installed to: %PLUGIN_OUT%
echo.
echo  ================================================
echo   Done! Start GTA 5 with LSPDFR and go on duty.
echo   You will see "BlueLineDispatch bridge active"
echo   in-game when the script loads.
echo  ================================================
echo.
pause
