@echo off
title BlueLineDispatch Plugin Builder
color 0A
echo.
echo  ================================================
echo   BlueLineDispatchPro -- Plugin Builder
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

:: ── Find RagePluginHook.dll (SDK file, not the .exe launcher) ────────────────
set RPH_DLL=
for %%F in (
    "%GTA_DIR%\RagePluginHook.dll"
    "%GTA_DIR%\RAGEPluginHook.dll"
    "%GTA_DIR%\plugins\RagePluginHook.dll"
    "%~dp0RagePluginHook.dll"
) do (
    if exist %%F set RPH_DLL=%%~F
)

if "%RPH_DLL%"=="" (
    echo.
    echo  [!] RagePluginHook.dll ^(the SDK file^) was not found.
    echo.
    echo      This is NOT the same as RagePluginHook.exe.
    echo      You need to download the SDK zip separately:
    echo.
    echo      1. Go to:  https://ragepluginhook.net/Downloads.aspx
    echo      2. Download the latest SDK zip
    echo      3. Extract RagePluginHook.dll from it
    echo      4. Put it in the same folder as this bat file:
    echo         %~dp0
    echo      5. Run this script again.
    echo.
    pause & exit /b 1
)
echo  [OK] RagePluginHook.dll: %RPH_DLL%

:: ── Find LSPDFR DLL ───────────────────────────────────────────────────────────
set LSPDFR_DLL=
for %%F in (
    "%GTA_DIR%\plugins\LSPDFR\LSPD First Response.dll"
    "%~dp0LSPD First Response.dll"
) do (
    if exist %%F set LSPDFR_DLL=%%~F
)

if "%LSPDFR_DLL%"=="" (
    echo [ERROR] LSPD First Response.dll not found.
    echo         Expected: %GTA_DIR%\plugins\LSPDFR\LSPD First Response.dll
    pause & exit /b 1
)
echo  [OK] LSPDFR DLL: %LSPDFR_DLL%

set "PLUGIN_OUT=%GTA_DIR%\plugins\LSPDFR\BlueLinePlugin.dll"
echo  [OK] LSPDFR DLLs found.
echo.
echo  Compiling BlueLinePlugin.cs...
echo.

:: ── Compile ──────────────────────────────────────────────────────────────────
"%CSC%" ^
    /target:library ^
    /optimize+ ^
    /out:"%~dp0BlueLinePlugin.dll" ^
    /reference:"%RPH_DLL%" ^
    /reference:"%LSPDFR_DLL%" ^
    /reference:"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.dll" ^
    /reference:"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Drawing.dll" ^
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
    echo [ERROR] Could not copy DLL to LSPDFR folder. Try running as Administrator.
    pause & exit /b 1
)

echo  [OK] Installed to: %PLUGIN_OUT%
echo.
echo  ================================================
echo   Done! Start GTA 5 with LSPDFR and go on duty.
echo   You will see "BlueLineDispatch bridge active"
echo   in-game when the plugin loads.
echo  ================================================
echo.
pause
