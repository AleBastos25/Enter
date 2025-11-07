# Guia de Instalação - Document Extraction System

Este guia fornece instruções passo a passo para instalar e configurar o sistema em diferentes plataformas.

##  Aviso 

**Validação de Instalação:**
- ✅ **Windows**: Instruções validadas e testadas na máquina do desenvolvedor
- ⚠️ **Linux e macOS**: Instruções baseadas em documentação e assistência de IA (GPT-5). **Não foram testadas em ambiente real**. Se encontrar problemas, por favor reporte ou ajuste conforme sua distribuição/versão do sistema operacional.

## Pré-requisitos

- **Python 3.10+** (recomendado: Python 3.11 ou 3.12)
- **Node.js 18+** e **npm** (apenas para interface web)
- **Git** (para clonar o repositório)

## Instalação por Plataforma

### Windows

#### 1. Instalar Python

**Opção A: Instalador Oficial (Recomendado)**

1. Baixe Python 3.11+ de https://www.python.org/downloads/
2. Durante a instalação:
   - ✅ Marque "Add Python to PATH"
   - ✅ Marque "Install pip"
3. Reinicie o PowerShell/Terminal
4. Verifique a instalação:
   ```powershell
   python --version
   pip --version
   ```

**Opção B: Chocolatey**

```powershell
choco install python311
```

**Opção C: winget**

```powershell
winget install Python.Python.3.11
```

#### 2. Instalar Node.js (para interface web)

**Opção A: Instalador Oficial**

1. Baixe Node.js LTS de https://nodejs.org/
2. Execute o instalador `.msi`
3. Durante a instalação:
   - ✅ Marque "Add to PATH"
4. Reinicie o PowerShell/Terminal
5. Verifique:
   ```powershell
   node --version
   npm --version
   ```

**Opção B: Chocolatey**

```powershell
choco install nodejs-lts
```

**Opção C: winget**

```powershell
winget install OpenJS.NodeJS.LTS
```

#### 3. Clonar e Configurar o Projeto

```powershell
# Clonar repositório (se aplicável)
git clone <url-do-repositorio>
cd Enter

# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# Se houver erro de política de execução, execute:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Instalar dependências Python
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 4. Configurar Secrets (Opcional - para LLM)

```powershell
# Copiar template de secrets
Copy-Item configs/secrets.yaml.example configs/secrets.yaml

# Editar e adicionar sua OPENAI_API_KEY
notepad configs/secrets.yaml
```

#### 5. Instalar Dependências do Frontend

```powershell
cd frontend
npm install
cd ..
```

#### 6. Verificar Instalação

```powershell
# Testar Python
python --version
python -c "import sys; print(sys.version)"

# Testar Node.js
node --version
npm --version

# Testar imports Python
python -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

### Linux (Ubuntu/Debian)

#### 1. Atualizar Sistema

```bash
sudo apt update
sudo apt upgrade -y
```

#### 2. Instalar Python 3.11+

```bash
# Instalar Python 3.11 e ferramentas
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Verificar instalação
python3.11 --version
pip3 --version
```

**Nota:** Se sua distribuição não tiver Python 3.11, use o deadsnakes PPA:

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

#### 3. Instalar Node.js 18+ (para interface web)

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

#### 4. Instalar Dependências do Sistema

```bash
# Dependências para compilação de pacotes Python
sudo apt install -y build-essential gcc g++ make

# Dependências para PDF processing (se necessário)
sudo apt install -y poppler-utils
```

#### 5. Clonar e Configurar o Projeto

```bash
# Clonar repositório (se aplicável)
git clone <url-do-repositorio>
cd Enter

# Criar ambiente virtual
python3.11 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar dependências Python
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 6. Configurar Secrets (Opcional - para LLM)

```bash
# Copiar template de secrets
cp configs/secrets.yaml.example configs/secrets.yaml

# Editar e adicionar sua OPENAI_API_KEY
nano configs/secrets.yaml
# ou
vim configs/secrets.yaml
```

#### 7. Instalar Dependências do Frontend

```bash
cd frontend
npm install
cd ..
```

#### 8. Verificar Instalação

```bash
# Testar Python
python3.11 --version
python3.11 -c "import sys; print(sys.version)"

# Testar Node.js
node --version
npm --version

# Testar imports Python
python3.11 -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

### macOS

#### 1. Instalar Homebrew (se não tiver)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Instalar Python 3.11+

```bash
# Instalar Python via Homebrew
brew install python@3.11

# Verificar instalação
python3.11 --version
pip3.11 --version

# Criar alias (opcional)
echo 'alias python3=python3.11' >> ~/.zshrc
echo 'alias pip3=pip3.11' >> ~/.zshrc
source ~/.zshrc
```

#### 3. Instalar Node.js 18+ (para interface web)

```bash
# Instalar Node.js LTS via Homebrew
brew install node@20

# Verificar
node --version
npm --version
```

**Alternativa: nvm**

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

#### 4. Instalar Dependências do Sistema

```bash
# Dependências para compilação (geralmente já instaladas com Xcode Command Line Tools)
xcode-select --install

# Dependências para PDF processing (se necessário)
brew install poppler
```

#### 5. Clonar e Configurar o Projeto

```bash
# Clonar repositório (se aplicável)
git clone <url-do-repositorio>
cd Enter

# Criar ambiente virtual
python3.11 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar dependências Python
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 6. Configurar Secrets (Opcional - para LLM)

```bash
# Copiar template de secrets
cp configs/secrets.yaml.example configs/secrets.yaml

# Editar e adicionar sua OPENAI_API_KEY
nano configs/secrets.yaml
# ou
open -a TextEdit configs/secrets.yaml
```

#### 7. Instalar Dependências do Frontend

```bash
cd frontend
npm install
cd ..
```

#### 8. Verificar Instalação

```bash
# Testar Python
python3.11 --version
python3.11 -c "import sys; print(sys.version)"

# Testar Node.js
node --version
npm --version

# Testar imports Python
python3.11 -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

## Configuração Pós-Instalação

### 1. Configurar Variáveis de Ambiente (Opcional)

Crie um arquivo `.env` na raiz do projeto:

```bash
# .env
OPENAI_API_KEY=sk-...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Testar Instalação

#### Teste Básico Python

```bash
# Ativar ambiente virtual primeiro
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

python scripts/batch_extract.py --help
```

#### Teste Backend

```bash
# Ativar ambiente virtual (se necessário)
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

# No diretório raiz do projeto
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# ou
python -m backend.src.main
```

Acesse `http://localhost:8000/docs` para ver a documentação da API.

#### Teste Frontend

```bash
cd frontend
npm run dev
```

Acesse `http://localhost:3000` no navegador.

---

## Scripts de Setup Automatizados

### Windows

```powershell
# Executar script de setup
.\scripts\check_setup.ps1
```

### Linux/Mac

```bash
# Criar script de setup (se necessário)
chmod +x scripts/check_setup.sh
./scripts/check_setup.sh
```

---

## Solução de Problemas

### Python não encontrado

**Windows:**
- Verifique se Python está no PATH
- Reinicie o terminal após instalar
- Use `py` ao invés de `python` se necessário

**Linux/Mac:**
- Use `python3.11` explicitamente
- Verifique com `which python3.11`

### pip não encontrado

```bash
# Windows
python -m ensurepip --upgrade

# Linux/Mac
python3.11 -m ensurepip --upgrade
```

### Erros de compilação (Linux/Mac)

```bash
# Instalar dependências de desenvolvimento
# Ubuntu/Debian
sudo apt install -y build-essential python3-dev

# macOS
xcode-select --install
```

### Node.js não encontrado

**Windows:**
- Reinicie o terminal após instalar
- Verifique PATH em variáveis de ambiente

**Linux/Mac:**
- Use `nvm` para gerenciar versões
- Verifique com `which node`

### Erros de permissão (Linux/Mac)

```bash
# Não use sudo com pip/npm quando em ambiente virtual
# Se necessário, ajuste permissões:
sudo chown -R $USER:$USER ~/.npm
```

### Porta já em uso

```bash
# Backend - usar outra porta (no diretório raiz do projeto)
uvicorn backend.src.main:app --port 8001

# Frontend - usar outra porta
cd frontend
npm run dev -- -p 3001
```

---

## Próximos Passos

Após a instalação bem-sucedida:

1. Leia o [README.md](README.md) para entender como usar o sistema
2. Consulte a seção "Como Utilizar a Solução" no README
3. Teste com os PDFs de exemplo em `data/samples/`
4. Configure sua `OPENAI_API_KEY` se quiser usar LLM fallback
5. 

