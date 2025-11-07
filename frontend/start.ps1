# Script para iniciar o frontend com Node.js

$nodePath = "C:\Users\aleba\Downloads\node-v24.11.0-win-x64"

# Adicionar Node.js ao PATH da sessão atual
if (Test-Path "$nodePath\node.exe") {
    $env:Path += ";$nodePath"
    Write-Host "✅ Node.js configurado para esta sessão"
} else {
    Write-Host "❌ Erro: Node.js não encontrado em $nodePath"
    Write-Host "Execute setup_node_path.ps1 primeiro"
    exit 1
}

# Verificar se estamos no diretório correto
if (-not (Test-Path "package.json")) {
    Write-Host "❌ Erro: package.json não encontrado"
    Write-Host "Execute este script do diretório frontend/"
    exit 1
}

# Verificar se node_modules existe
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Instalando dependências..."
    npm install
}

# Iniciar servidor de desenvolvimento
Write-Host "🚀 Iniciando servidor de desenvolvimento..."
npm run dev

