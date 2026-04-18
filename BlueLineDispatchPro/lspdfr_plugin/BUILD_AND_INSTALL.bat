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

:: ── Find RagePluginHook SDK assembly ─────────────────────────────────────────
:: The real SDK file is RagePluginHookSDK.dll inside a "SDK" subfolder of GTA V
set RPH_DLL=

:: Check local plugin folder first (previously copied)
if exist "%~dp0RagePluginHookSDK.dll"     set RPH_DLL=%~dp0RagePluginHookSDK.dll
if exist "%~dp0RagePluginHook.dll"        set RPH_DLL=%~dp0RagePluginHook.dll

:: Check GTA SDK subfolder (standard RPH install location)
if "%RPH_DLL%"=="" (
    if exist "%GTA_DIR%\SDK\RagePluginHookSDK.dll" set RPH_DLL=%GTA_DIR%\SDK\RagePluginHookSDK.dll
)
if "%RPH_DLL%"=="" (
    if exist "%GTA_DIR%\SDK\RagePluginHook.dll"    set RPH_DLL=%GTA_DIR%\SDK\RagePluginHook.dll
)

:: Check NuGet package SDK folder
if "%RPH_DLL%"=="" (
    if exist "%~dp0rph_sdk\SDK\RagePluginHookSDK.dll" (
        copy /Y "%~dp0rph_sdk\SDK\RagePluginHookSDK.dll" "%~dp0RagePluginHookSDK.dll" >nul
        set RPH_DLL=%~dp0RagePluginHookSDK.dll
    )
)
if "%RPH_DLL%"=="" (
    if exist "%~dp0rph_sdk\lib\net472\RagePluginHook.dll" (
        copy /Y "%~dp0rph_sdk\lib\net472\RagePluginHook.dll" "%~dp0RagePluginHook.dll" >nul
        set RPH_DLL=%~dp0RagePluginHook.dll
    )
)

:: Broad search: scan entire GTA folder for SDK dll (any name)
if "%RPH_DLL%"=="" (
    echo  [!] Scanning GTA folder for RPH SDK...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$hits = Get-ChildItem -Path '%GTA_DIR%' -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'RagePluginHook' -and $_.Extension -eq '.dll' };" ^
        "if ($hits) { $hits[0].FullName } else { 'NOTFOUND' }" > "%~dp0rph_path.txt"
    set /p RPH_DLL=<"%~dp0rph_path.txt"
    del "%~dp0rph_path.txt" >nul 2>&1
    if "%RPH_DLL%"=="NOTFOUND" set RPH_DLL=
)

:: Download from NuGet (full package, check SDK folder inside it)
if "%RPH_DLL%"=="" (
    echo  [!] Downloading RPH SDK from NuGet...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$zip='%~dp0rph_sdk.zip';" ^
        "Invoke-WebRequest -Uri 'https://www.nuget.org/api/v2/package/RagePluginHook/1.124.0' -OutFile $zip;" ^
        "Expand-Archive -Path $zip -DestinationPath '%~dp0rph_sdk' -Force;" ^
        "$dll = Get-ChildItem -Path '%~dp0rph_sdk' -Recurse -Filter '*.dll' | Where-Object { $_.Name -match 'RagePluginHook' } | Select-Object -First 1;" ^
        "if ($dll) { Write-Host ('Found: ' + $dll.FullName); Copy-Item $dll.FullName '%~dp0RagePluginHook.dll' -Force }"
    if exist "%~dp0RagePluginHook.dll" set RPH_DLL=%~dp0RagePluginHook.dll
)

if "%RPH_DLL%"=="" (
    echo.
    echo  [!] RPH SDK not found. Manual step needed:
    echo.
    echo      Look in your GTA V folder for a subfolder called "SDK"
    echo      Inside it should be RagePluginHookSDK.dll
    echo      Copy it to: %~dp0RagePluginHookSDK.dll
    echo      Then run this script again.
    echo.
    echo      If no SDK folder exists, re-download LSPDFR from:
    echo      https://www.lcpdfr.com/downloads/gta5mods/g17media/7792-lspd-first-response/
    echo      The zip contains the SDK folder.
    echo.
    pause & exit /b 1
)
echo  [OK] RPH SDK: %RPH_DLL%

:: ── Find LSPDFR DLL ───────────────────────────────────────────────────────────
set LSPDFR_DLL=
for %%F in (
    "%GTA_DIR%\plugins\LSPDFR\LSPD First Response.dll"
    "%GTA_DIR%\LSPD First Response.dll"
    "%~dp0LSPD First Response.dll"
) do (
    if exist "%%~F" set LSPDFR_DLL=%%~F
)

if "%LSPDFR_DLL%"=="" (
    echo  [!] LSPD First Response.dll not found in known paths -- searching GTA folder...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$dll = Get-ChildItem -Path '%GTA_DIR%' -Recurse -Filter 'LSPD First Response.dll' -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
        "if ($dll) { $dll.FullName } else { 'NOTFOUND' }" > "%~dp0lspdfr_path.txt"
    set /p LSPDFR_DLL=<"%~dp0lspdfr_path.txt"
    del "%~dp0lspdfr_path.txt" >nul 2>&1
)

if "%LSPDFR_DLL%"=="NOTFOUND" set LSPDFR_DLL=
if "%LSPDFR_DLL%"=="" (
    echo [ERROR] LSPD First Response.dll not found anywhere in %GTA_DIR%
    echo         Is LSPDFR installed? Download from lspdfr.com
    pause & exit /b 1
)
echo  [OK] LSPDFR DLL: %LSPDFR_DLL%

:: Install next to LSPD First Response.dll, wherever it was found
for %%F in ("%LSPDFR_DLL%") do set "PLUGIN_OUT=%%~dpFBlueLinePlugin.dll"
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
