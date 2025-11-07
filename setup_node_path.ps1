# Script para configurar Node.js no PATH (se necessário)

$nodePath = "C:\Users\aleba\Downloads\node-v24.11.0-win-x64"

# Verificar se node.exe existe
if (Test-Path "$nodePath\node.exe") {
    Write-Host "Node.js encontrado em: $nodePath"
    
    # Adicionar ao PATH do usuário (permanente)
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$nodePath*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$nodePath", "User")
        Write-Host "✅ Node.js adicionado ao PATH do usuário (permanente)"
    } else {
        Write-Host "✅ Node.js já está no PATH do usuário"
    }
    
    # Adicionar ao PATH da sessão atual (temporário)
    $env:Path += ";$nodePath"
    Write-Host "✅ Node.js adicionado ao PATH da sessão atual"
    
    # Verificar instalação
    Write-Host "`nVerificando instalação..."
    $nodeVersion = & "$nodePath\node.exe" --version
    $npmVersion = & "$nodePath\npm.cmd" --version
    Write-Host "Node.js: $nodeVersion"
    Write-Host "npm: $npmVersion"
    Write-Host "`n✅ Tudo configurado! Reinicie o PowerShell para aplicar mudanças permanentes."
} else {
    Write-Host "❌ Erro: node.exe não encontrado em $nodePath"
    Write-Host "Verifique se o caminho está correto."
}

