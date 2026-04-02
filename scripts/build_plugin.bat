@echo off
echo ========================================
echo  Building LSPDFR Dispatch Plugin DLL
echo ========================================
echo.
echo PREREQUISITES:
echo   1. .NET SDK installed (dotnet command available)
echo   2. Copy these DLLs to plugin\lib\:
echo      - RagePluginHook.dll (from GTA V root)
echo      - LSPD First Response.dll (from GTA V\Plugins\LSPD First Response\)
echo.

cd /d "%~dp0\..\plugin"

REM Check for lib DLLs
if not exist "lib\RagePluginHook.dll" (
    echo ERROR: lib\RagePluginHook.dll not found!
    echo Copy it from your GTA V installation directory.
    pause
    exit /b 1
)
if not exist "lib\LSPD First Response.dll" (
    echo ERROR: lib\LSPD First Response.dll not found!
    echo Copy it from GTA V\Plugins\LSPD First Response\
    pause
    exit /b 1
)

dotnet build -c Release

echo.
echo Build complete! DLL is at: bin\Release\net48\LSPDFRDispatch.dll
echo.
echo To install, copy these to your GTA V\Plugins\ folder:
echo   - bin\Release\net48\LSPDFRDispatch.dll
echo   - bin\Release\net48\Newtonsoft.Json.dll
echo.
echo Also copy LSPDFRDispatch.ini to GTA V\Plugins\
echo.
pause
