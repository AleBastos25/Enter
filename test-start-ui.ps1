# Script de teste para verificar configuração antes de iniciar
# Execute: .\test-start-ui.ps1

Write-Host "🔍 Verificando configuração..." -ForegroundColor Cyan
Write-Host ""

# Verificar Node.js
$nodePath = "C:\Program Files\node-v24.11.0-win-x64"
$nodePathDownloads = "C:\Users\aleba\Downloads\node-v24.11.0-win-x64"

$nodeFound = $false
if (Test-Path "$nodePath\node.exe") {
    Write-Host "✅ Node.js encontrado em: $nodePath" -ForegroundColor Green
    $nodeFound = $true
    $actualPath = $nodePath
} elseif (Test-Path "$nodePathDownloads\node.exe") {
    Write-Host "✅ Node.js encontrado em: $nodePathDownloads" -ForegroundColor Green
    $nodeFound = $true
    $actualPath = $nodePathDownloads
} else {
    Write-Host "❌ Node.js NÃO encontrado!" -ForegroundColor Red
    Write-Host "   Procurei em:" -ForegroundColor Yellow
    Write-Host "   - $nodePath" -ForegroundColor Yellow
    Write-Host "   - $nodePathDownloads" -ForegroundColor Yellow
}

if ($nodeFound) {
    $env:Path += ";$actualPath"
    try {
        $nodeVersion = & "$actualPath\node.exe" --version
        Write-Host "✅ Node.js versão: $nodeVersion" -ForegroundColor Green
        
        $npmVersion = & "$actualPath\npm.cmd" --version 2>$null
        Write-Host "✅ npm versão: $npmVersion" -ForegroundColor Green
    } catch {
        Write-Host "❌ Erro ao verificar Node.js: $_" -ForegroundColor Red
    }
}

Write-Host ""

# Verificar diretório do projeto
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "📁 Diretório do projeto: $projectRoot" -ForegroundColor Cyan

# Verificar backend
$backendDir = Join-Path $projectRoot "backend"
if (Test-Path $backendDir) {
    Write-Host "✅ Diretório backend encontrado" -ForegroundColor Green
} else {
    Write-Host "❌ Diretório backend NÃO encontrado" -ForegroundColor Red
}

# Verificar frontend
$frontendDir = Join-Path $projectRoot "frontend"
if (Test-Path $frontendDir) {
    Write-Host "✅ Diretório frontend encontrado" -ForegroundColor Green
    
    $packageJson = Join-Path $frontendDir "package.json"
    if (Test-Path $packageJson) {
        Write-Host "✅ package.json encontrado" -ForegroundColor Green
        
        $nodeModules = Join-Path $frontendDir "node_modules"
        if (Test-Path $nodeModules) {
            Write-Host "✅ node_modules encontrado (dependências instaladas)" -ForegroundColor Green
        } else {
            Write-Host "⚠️  node_modules NÃO encontrado (precisa instalar dependências)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ package.json NÃO encontrado" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Diretório frontend NÃO encontrado" -ForegroundColor Red
}

# Verificar ambiente virtual Python
$venvPath = Join-Path $projectRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "✅ Ambiente virtual Python encontrado" -ForegroundColor Green
} else {
    Write-Host "⚠️  Ambiente virtual Python NÃO encontrado (opcional)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Pressione qualquer tecla para continuar..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")


