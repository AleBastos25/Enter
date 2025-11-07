# Setup do Frontend - Graph Extractor UI

##  Aviso 

**Validação de Instalação:**
- ✅ **Windows**: Instruções validadas e testadas na máquina do desenvolvedor
- ⚠️ **Linux e macOS**: Instruções baseadas em documentação e assistência de IA (GPT-5). **Não foram testadas em ambiente real**. Se encontrar problemas, por favor reporte ou ajuste conforme sua distribuição/versão do sistema operacional.

## ⚠️ Node.js Necessário

O frontend requer **Node.js 18+** e **npm** (vem junto com Node.js).

## Instalação do Node.js

### Windows

1. **Baixe o Node.js LTS**:
   - Acesse: https://nodejs.org/
   - Baixe a versão LTS (recomendada)
   - Execute o instalador `.msi`

2. **Durante a instalação**:
   - ✅ Marque "Add to PATH"
   - ✅ Marque "Automatically install necessary tools"

3. **Reinicie o PowerShell/Terminal**

4. **Verifique a instalação**:
   ```powershell
   node --version
   npm --version
   ```

**Alternativas:**

- **Chocolatey:**
  ```powershell
  choco install nodejs-lts
  ```

- **winget:**
  ```powershell
  winget install OpenJS.NodeJS.LTS
  ```

### Linux (Ubuntu/Debian)

**Opção A: NodeSource (Recomendado)**

```bash
# Instalar Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verificar
node --version
npm --version
```

**Opção B: nvm (Node Version Manager)**

```bash
# Instalar nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Recarregar shell
source ~/.bashrc

# Instalar Node.js LTS
nvm install --lts
nvm use --lts

# Verificar
node --version
npm --version
```

**Opção C: Snap**

```bash
sudo snap install node --classic
```

### macOS

**Opção A: Homebrew (Recomendado)**

```bash
# Instalar Node.js LTS via Homebrew
brew install node@20

# Verificar
node --version
npm --version
```

**Opção B: nvm**

```bash
# Instalar nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Recarregar shell
source ~/.zshrc

# Instalar Node.js LTS
nvm install --lts
nvm use --lts

# Verificar
node --version
npm --version
```

**Opção C: Instalador Oficial**

1. Baixe de https://nodejs.org/
2. Execute o instalador `.pkg`
3. Siga as instruções do instalador

## Instalação das Dependências

Após instalar o Node.js:

**Windows:**
```powershell
cd frontend
npm install
```

**Linux/Mac:**
```bash
cd frontend
npm install
```

Isso irá instalar:
- Next.js
- React
- TypeScript
- TailwindCSS
- Axios
- JSZip

## Execução

**Windows:**
```powershell
# Desenvolvimento
npm run dev

# Build de produção
npm run build

# Executar produção
npm start
```

**Linux/Mac:**
```bash
# Desenvolvimento
npm run dev

# Build de produção
npm run build

# Executar produção
npm start
```

## Configuração

Crie um arquivo `.env.local` (opcional):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Se o backend estiver em outra porta, ajuste conforme necessário.

## Problemas Comuns

### "npm não é reconhecido"

- Node.js não está instalado
- Node.js não está no PATH
- Reinicie o terminal após instalar

### Erro de módulos não encontrados

**Windows:**
```powershell
# Limpar cache e reinstalar
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
```

**Linux/Mac:**
```bash
# Limpar cache e reinstalar
rm -rf node_modules package-lock.json
npm install
```

### Porta 3000 ocupada

**Windows:**
```powershell
npm run dev -- -p 3001
```

**Linux/Mac:**
```bash
npm run dev -- -p 3001
```

### Problemas de permissão (Linux/Mac)

```bash
# Ajustar permissões do npm
sudo chown -R $USER:$USER ~/.npm
```

