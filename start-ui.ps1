# Script para iniciar a UI completa (Backend + Frontend)
# Execute: .\start-ui.ps1

# Configurar encoding UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Nao fechar automaticamente em caso de erro
$ErrorActionPreference = "Continue"

# Funcao para pausar e aguardar tecla
function Pause-Script {
    Write-Host ""
    Write-Host "Pressione qualquer tecla para continuar..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host "Iniciando Graph Extractor UI..." -ForegroundColor Green
Write-Host ""

# Configurar Node.js
$nodePath = "C:\Program Files\node-v24.11.0-win-x64"
$nodePathDownloads = "C:\Users\aleba\Downloads\node-v24.11.0-win-x64"

# Tentar encontrar Node.js
if (Test-Path "$nodePath\node.exe") {
    Write-Host "[OK] Node.js encontrado em: $nodePath" -ForegroundColor Green
} elseif (Test-Path "$nodePathDownloads\node.exe") {
    Write-Host "[OK] Node.js encontrado em: $nodePathDownloads" -ForegroundColor Green
    $nodePath = $nodePathDownloads
} else {
    Write-Host "[ERRO] Node.js nao encontrado!" -ForegroundColor Red
    Write-Host "Procurei em:" -ForegroundColor Yellow
    Write-Host "  - $nodePath" -ForegroundColor Yellow
    Write-Host "  - $nodePathDownloads" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Dica: Instale o Node.js ou ajuste o caminho no script." -ForegroundColor Yellow
    Pause-Script
    exit 1
}

# Adicionar Node.js ao PATH da sessao
$env:Path += ";$nodePath"

# Verificar Node.js e npm
try {
    $nodeVersion = & "$nodePath\node.exe" --version
    Write-Host "[OK] Node.js: $nodeVersion" -ForegroundColor Green
    
    # Tentar npm.cmd se npm.ps1 falhar
    try {
        $npmVersion = & "$nodePath\npm.cmd" --version 2>$null
        Write-Host "[OK] npm: $npmVersion" -ForegroundColor Green
        $npmCmd = "npm.cmd"
    } catch {
        Write-Host "[AVISO] npm nao disponivel como comando, usando npm.cmd" -ForegroundColor Yellow
        $npmCmd = "npm.cmd"
    }
} catch {
    Write-Host "[ERRO] Erro ao verificar Node.js: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Dica: Verifique se o Node.js esta instalado corretamente." -ForegroundColor Yellow
    Pause-Script
    exit 1
}

# Navegar para o diretorio do projeto
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
Write-Host "[INFO] Diretorio do projeto: $projectRoot" -ForegroundColor Cyan
Write-Host ""

# Funcao para verificar se porta esta em uso
function Test-Port {
    param([int]$Port)
    try {
        $connection = Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue -InformationLevel Quiet
        return $connection
    } catch {
        return $false
    }
}

# Verificar e iniciar Backend
Write-Host "Verificando Backend..." -ForegroundColor Cyan
$backendPort = 8000
$backendRunning = Test-Port -Port $backendPort

if ($backendRunning) {
    Write-Host "[OK] Backend ja esta rodando na porta $backendPort" -ForegroundColor Green
} else {
    Write-Host "Iniciando Backend..." -ForegroundColor Yellow
    
    # Verificar se ambiente virtual existe
    $venvPath = Join-Path $projectRoot ".venv"
    if (Test-Path $venvPath) {
        Write-Host "[INFO] Ativando ambiente virtual..." -ForegroundColor Cyan
    }
    
    # Iniciar backend em nova janela do PowerShell
    # Comando do backend com logs forçados e unbuffered
    $backendCommand = "cd '$projectRoot'; if (Test-Path '.venv') { .venv\Scripts\Activate.ps1 }; `$env:PYTHONUNBUFFERED='1'; python -u -m uvicorn backend.src.main:app --reload --host 0.0.0.0 --port $backendPort --log-level debug"
    
    # Criar arquivo de log para o backend
    $backendLogFile = Join-Path $projectRoot "backend.log"
    Write-Host "[INFO] Logs do backend serão salvos em: $backendLogFile" -ForegroundColor Cyan
    
    # Iniciar backend redirecionando output para arquivo E console
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "$backendCommand *>&1 | Tee-Object -FilePath '$backendLogFile'"
    Write-Host "[INFO] Aguardando backend iniciar..." -ForegroundColor Yellow
    
    # Aguardar backend iniciar (ate 30 segundos)
    $timeout = 30
    $elapsed = 0
    while (-not (Test-Port -Port $backendPort) -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 2
        $elapsed += 2
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""
    
    if (Test-Port -Port $backendPort) {
        Write-Host "[OK] Backend iniciado com sucesso!" -ForegroundColor Green
    } else {
        Write-Host "[AVISO] Backend pode nao ter iniciado. Verifique a janela do backend." -ForegroundColor Yellow
        Write-Host "Dica: Tente iniciar manualmente: uvicorn backend.src.main:app --reload --port $backendPort" -ForegroundColor Yellow
    }
}

Write-Host ""

# Verificar e iniciar Frontend
Write-Host "Verificando Frontend..." -ForegroundColor Cyan
$frontendPort = 3000
$frontendDir = Join-Path $projectRoot "frontend"

if (-not (Test-Path $frontendDir)) {
    Write-Host "[ERRO] Diretorio frontend nao encontrado!" -ForegroundColor Red
    Write-Host "Dica: Certifique-se de estar na raiz do projeto." -ForegroundColor Yellow
    Pause-Script
    exit 1
}

Set-Location $frontendDir

# Verificar se node_modules existe
if (-not (Test-Path "node_modules")) {
    Write-Host "Instalando dependencias do frontend..." -ForegroundColor Yellow
    & "$nodePath\$npmCmd" install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Erro ao instalar dependencias!" -ForegroundColor Red
        Write-Host "Dica: Tente executar manualmente: cd frontend && npm install" -ForegroundColor Yellow
        Pause-Script
        exit 1
    }
}

# Verificar se frontend ja esta rodando
$frontendRunning = Test-Port -Port $frontendPort

if ($frontendRunning) {
    Write-Host "[OK] Frontend ja esta rodando na porta $frontendPort" -ForegroundColor Green
    Write-Host "[INFO] Abra http://localhost:$frontendPort no navegador" -ForegroundColor Cyan
} else {
    Write-Host "Iniciando Frontend..." -ForegroundColor Yellow
    
    # Aguardar um pouco para garantir que o backend esta pronto
    Start-Sleep -Seconds 2
    
    # Abrir navegador apos 5 segundos
    Start-Job -ScriptBlock {
        Start-Sleep -Seconds 5
        Start-Process "http://localhost:3000"
    } | Out-Null
    
    Write-Host ""
    Write-Host "===========================================================" -ForegroundColor Cyan
    Write-Host "[OK] Backend: http://localhost:$backendPort" -ForegroundColor Green
    Write-Host "[OK] Frontend: http://localhost:$frontendPort" -ForegroundColor Green
    Write-Host "[INFO] Navegador sera aberto automaticamente em alguns segundos..." -ForegroundColor Cyan
    Write-Host "[INFO] Para parar, pressione Ctrl+C" -ForegroundColor Yellow
    Write-Host "===========================================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Iniciar frontend (bloqueia ate Ctrl+C)
    try {
        & "$nodePath\$npmCmd" run dev
    } catch {
        Write-Host ""
        Write-Host "[ERRO] Erro ao iniciar frontend: $_" -ForegroundColor Red
        Write-Host "Dica: Verifique se as dependencias estao instaladas." -ForegroundColor Yellow
        Pause-Script
    }
}
