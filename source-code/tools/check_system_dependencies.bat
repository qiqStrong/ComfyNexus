@echo off
chcp 65001 >nul
title Comfyui-Box System Dependency Checker

echo ============================================================
echo  Comfyui-Box Windows System Dependency Checker
echo ============================================================
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0check_system_dependencies.ps1" -Detailed

exit /b %ERRORLEVEL%
