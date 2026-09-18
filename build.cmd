@echo off
:: ============================================================
::  DOSOFT - Script de compilation PyInstaller
::  Prerequis : pip install pyinstaller
:: ============================================================
setlocal enabledelayedexpansion

set APP_NAME=Dosoft_BETA
set MAIN_FILE=main.py
set ICON_FILE=logo.ico
set OUT_DIR=dist
set TCL_LIBRARY=%~dp0..\python313-tcl\tcl8.6
set TK_LIBRARY=%~dp0..\python313-tcl\tk8.6

echo.
echo  ============================
echo   Compilation PyInstaller - DOSOFT
echo  ============================
echo.

if exist "%OUT_DIR%" (
    echo [*] Nettoyage du dossier dist...
    rmdir /s /q "%OUT_DIR%"
)
if exist "build" (
    rmdir /s /q "build"
)
if exist "%APP_NAME%.spec" (
    del "%APP_NAME%.spec"
)

:: --- Compilation PyInstaller ---
echo [*] Lancement de PyInstaller...
python -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --uac-admin ^
    --additional-hooks-dir="hooks" ^
    --icon="%ICON_FILE%" ^
    --name="%APP_NAME%" ^
    --distpath="%OUT_DIR%" ^
    --add-data="skin;skin" ^
    --add-data="sounds;sounds" ^
    --add-data="resources\\i18n;resources\\i18n" ^
    --add-data="resources\\keyboards;resources\\keyboards" ^
    --add-data="resources\\skin;resources\\skin" ^
    --add-data="..\\python313-tcl\\tcl8.6;tcl8.6" ^
    --add-data="..\\python313-tcl\\tk8.6;tk8.6" ^
    --add-binary="%LOCALAPPDATA%\\Programs\\Python\\Python313\\DLLs\\_tkinter.pyd;." ^
    --add-binary="%LOCALAPPDATA%\\Programs\\Python\\Python313\\DLLs\\tcl86t.dll;." ^
    --add-binary="%LOCALAPPDATA%\\Programs\\Python\\Python313\\DLLs\\tk86t.dll;." ^
    --add-data="logo.ico;." ^
    --add-data="version.json;." ^
    --hidden-import=customtkinter ^
    --hidden-import=PIL ^
    --hidden-import=pygame ^
    --hidden-import=win32api ^
    --hidden-import=win32con ^
    --hidden-import=win32gui ^
    --hidden-import=win32process ^
    --hidden-import=keyboard ^
    --hidden-import=tkinter ^
    --hidden-import=_tkinter ^
    --collect-all=customtkinter ^
    --collect-all=tkinter ^
    "%MAIN_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERREUR] La compilation a echoue. Verifiez les logs ci-dessus.
    pause
    exit /b 1
)

echo.
echo [OK] Compilation reussie !
echo [OK] Executable : %OUT_DIR%\%APP_NAME%.exe
echo.
pause
