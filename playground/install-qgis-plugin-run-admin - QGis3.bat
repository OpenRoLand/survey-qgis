@echo off
setlocal

:: ---- CONFIGURE THESE ----
set PLUGIN_NAME=siscadro_survey
set DEV_DIR=D:\prog\__py_libs__\siscadro-survey-qgis
set QGIS_PLUGIN_DIR=%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins
set TARGET_DIR=%QGIS_PLUGIN_DIR%\%PLUGIN_NAME%

echo.
echo ===== QGIS Plugin Junction Creator =====
echo.

:: ---- CHECK ADMIN ----
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click the .bat file and choose "Run as administrator".
    pause
    exit /b 1
)

:: ---- CHECK DEV DIR ----
if not exist "%DEV_DIR%" (
    echo ERROR: DEV_DIR does not exist:
    echo        %DEV_DIR%
    pause
    exit /b 1
)

:: ---- CHECK QGIS PLUGIN DIR ----
if not exist "%QGIS_PLUGIN_DIR%" (
    echo ERROR: QGIS_PLUGIN_DIR does not exist:
    echo        %QGIS_PLUGIN_DIR%
    pause
    exit /b 1
)

:: ---- REMOVE EXISTING FOLDER/LINK ----
if exist "%TARGET_DIR%" (
    echo Removing existing plugin folder/link:
    echo        %TARGET_DIR%
    rmdir "%TARGET_DIR%"
)

:: ---- CREATE JUNCTION ----
echo Creating junction:
echo    From: %DEV_DIR%
echo    To:   %TARGET_DIR%
echo.

mklink /J "%TARGET_DIR%" "%DEV_DIR%"

if %errorLevel% neq 0 (
    echo.
    echo ERROR: Failed to create junction.
    pause
    exit /b 1
)

echo.
echo SUCCESS: Junction created successfully!
pause
:: C:\Users\Nicu\AppData\Roaming\QGIS\QGIS4\profiles-old\default\python\plugins
:: C:\Users\Nicu\AppData\Roaming\QGIS\QGIS4\profiles\default\python\plugins