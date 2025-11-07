@echo off
REM Script para iniciar a UI completa (Backend + Frontend)
REM Execute: start-ui.bat

echo ========================================
echo Graph Extractor UI - Iniciando...
echo ========================================
echo.

REM Verificar se o arquivo PowerShell existe
if not exist "%~dp0start-ui.ps1" (
    echo ERRO: Arquivo start-ui.ps1 nao encontrado!
    echo.
    pause
    exit /b 1
)

REM Executar script PowerShell e manter janela aberta
powershell.exe -ExecutionPolicy Bypass -NoExit -File "%~dp0start-ui.ps1"

REM Se houver erro, aguardar antes de fechar
if errorlevel 1 (
    echo.
    echo Ocorreu um erro. Verifique a mensagem acima.
    echo.
    pause
)
