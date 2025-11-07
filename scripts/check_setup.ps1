# Script de verificação de setup para Windows PowerShell

Write-Host "=== Verificação de Setup - Graph Extractor UI ===" -ForegroundColor Cyan
Write-Host ""

# Verificar Node.js
Write-Host "Verificando Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "  ✓ Node.js instalado: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Node.js NÃO encontrado" -ForegroundColor Red
    Write-Host "    Instale em: https://nodejs.org/" -ForegroundColor Yellow
    $nodeOk = $false
}

# Verificar npm
Write-Host "Verificando npm..." -ForegroundColor Yellow
try {
    $npmVersion = npm --version
    Write-Host "  ✓ npm instalado: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ npm NÃO encontrado" -ForegroundColor Red
    Write-Host "    npm geralmente vem com Node.js" -ForegroundColor Yellow
    $npmOk = $false
}

# Verificar Python
Write-Host "Verificando Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "  ✓ Python instalado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python NÃO encontrado" -ForegroundColor Red
    Write-Host "    Instale em: https://www.python.org/downloads/" -ForegroundColor Yellow
    $pythonOk = $false
}

# Verificar pip
Write-Host "Verificando pip..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version
    Write-Host "  ✓ pip instalado" -ForegroundColor Green
} catch {
    Write-Host "  ✗ pip NÃO encontrado" -ForegroundColor Red
    Write-Host "    pip geralmente vem com Python" -ForegroundColor Yellow
    $pipOk = $false
}

# Verificar estrutura de diretórios
Write-Host ""
Write-Host "Verificando estrutura do projeto..." -ForegroundColor Yellow

$dirs = @("backend", "frontend", "src")
foreach ($dir in $dirs) {
    if (Test-Path $dir) {
        Write-Host "  ✓ Diretório $dir existe" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Diretório $dir NÃO encontrado" -ForegroundColor Red
    }
}

# Verificar arquivos de dependências
Write-Host ""
Write-Host "Verificando arquivos de dependências..." -ForegroundColor Yellow

if (Test-Path "backend/requirements.txt") {
    Write-Host "  ✓ backend/requirements.txt existe" -ForegroundColor Green
} else {
    Write-Host "  ✗ backend/requirements.txt NÃO encontrado" -ForegroundColor Red
}

if (Test-Path "frontend/package.json") {
    Write-Host "  ✓ frontend/package.json existe" -ForegroundColor Green
} else {
    Write-Host "  ✗ frontend/package.json NÃO encontrado" -ForegroundColor Red
}

# Verificar ambiente virtual
Write-Host ""
Write-Host "Verificando ambiente virtual..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "  ✓ Ambiente virtual .venv existe" -ForegroundColor Green
    Write-Host "    Para ativar: .venv\Scripts\Activate.ps1" -ForegroundColor Cyan
} else {
    Write-Host "  ⚠ Ambiente virtual .venv NÃO encontrado" -ForegroundColor Yellow
    Write-Host "    Para criar: python -m venv .venv" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Fim da Verificação ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor Yellow
Write-Host "1. Instale Node.js se necessário: https://nodejs.org/" -ForegroundColor White
Write-Host "2. Instale dependências do backend: pip install -r backend/requirements.txt" -ForegroundColor White
Write-Host "3. Instale dependências do frontend: cd frontend && npm install" -ForegroundColor White
Write-Host "4. Veja SETUP.md para mais detalhes" -ForegroundColor White

