# Installation Guide - Document Extraction System

This guide provides step-by-step instructions to install and configure the system on different platforms.

## Prerequisites

- **Python 3.10+** (recommended: Python 3.11 or 3.12)
- **Node.js 18+** and **npm** (only for web interface)
- **Git** (to clone the repository)

## Installation by Platform

### Windows

#### 1. Install Python

**Option A: Official Installer (Recommended)**

1. Download Python 3.11+ from https://www.python.org/downloads/
2. During installation:
   - ✅ Check "Add Python to PATH"
   - ✅ Check "Install pip"
3. Restart PowerShell/Terminal
4. Verify installation:
   ```powershell
   python --version
   pip --version
   ```

**Option B: Chocolatey**

```powershell
choco install python311
```

**Option C: winget**

```powershell
winget install Python.Python.3.11
```

#### 2. Install Node.js (for web interface)

**Option A: Official Installer**

1. Download Node.js LTS from https://nodejs.org/
2. Run the `.msi` installer
3. During installation:
   - ✅ Check "Add to PATH"
4. Restart PowerShell/Terminal
5. Verify:
   ```powershell
   node --version
   npm --version
   ```

**Option B: Chocolatey**

```powershell
choco install nodejs-lts
```

**Option C: winget**

```powershell
winget install OpenJS.NodeJS.LTS
```

#### 3. Clone and Configure the Project

```powershell
# Clone repository (if applicable)
git clone <url-do-repositorio>
cd Enter

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# If there's an execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 4. Configure Secrets (Optional - for LLM)

```powershell
# Copy secrets template
Copy-Item configs/secrets.yaml.example configs/secrets.yaml

# Edit and add your OPENAI_API_KEY
notepad configs/secrets.yaml
```

#### 5. Install Frontend Dependencies

```powershell
cd frontend
npm install
cd ..
```

#### 6. Verify Installation

```powershell
# Test Python
python --version
python -c "import sys; print(sys.version)"

# Test Node.js
node --version
npm --version

# Test Python imports
python -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

### Linux (Ubuntu/Debian)

#### 1. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

#### 2. Install Python 3.11+

```bash
# Install Python 3.11 and tools
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Verify installation
python3.11 --version
pip3 --version
```

**Note:** If your distribution doesn't have Python 3.11, use the deadsnakes PPA:

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

#### 3. Install Node.js 18+ (for web interface)

**Option A: NodeSource (Recommended)**

```bash
# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version
npm --version
```

**Option B: nvm (Node Version Manager)**

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Reload shell
source ~/.bashrc

# Install Node.js LTS
nvm install --lts
nvm use --lts

# Verify
node --version
npm --version
```

#### 4. Install System Dependencies

```bash
# Dependencies for Python package compilation
sudo apt install -y build-essential gcc g++ make

# Dependencies for PDF processing (if needed)
sudo apt install -y poppler-utils
```

#### 5. Clone and Configure the Project

```bash
# Clone repository (if applicable)
git clone <url-do-repositorio>
cd Enter

# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Update pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 6. Configure Secrets (Optional - for LLM)

```bash
# Copy secrets template
cp configs/secrets.yaml.example configs/secrets.yaml

# Edit and add your OPENAI_API_KEY
nano configs/secrets.yaml
# or
vim configs/secrets.yaml
```

#### 7. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

#### 8. Verify Installation

```bash
# Test Python
python3.11 --version
python3.11 -c "import sys; print(sys.version)"

# Test Node.js
node --version
npm --version

# Test Python imports
python3.11 -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

### macOS

#### 1. Install Homebrew (if you don't have it)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. Install Python 3.11+

```bash
# Install Python via Homebrew
brew install python@3.11

# Verify installation
python3.11 --version
pip3.11 --version

# Create alias (optional)
echo 'alias python3=python3.11' >> ~/.zshrc
echo 'alias pip3=pip3.11' >> ~/.zshrc
source ~/.zshrc
```

#### 3. Install Node.js 18+ (for web interface)

```bash
# Install Node.js LTS via Homebrew
brew install node@20

# Verify
node --version
npm --version
```

**Alternative: nvm**

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

# Reload shell
source ~/.zshrc

# Install Node.js LTS
nvm install --lts
nvm use --lts

# Verify
node --version
npm --version
```

#### 4. Install System Dependencies

```bash
# Dependencies for compilation (usually already installed with Xcode Command Line Tools)
xcode-select --install

# Dependencies for PDF processing (if needed)
brew install poppler
```

#### 5. Clone and Configure the Project

```bash
# Clone repository (if applicable)
git clone <url-do-repositorio>
cd Enter

# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Update pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### 6. Configure Secrets (Optional - for LLM)

```bash
# Copy secrets template
cp configs/secrets.yaml.example configs/secrets.yaml

# Edit and add your OPENAI_API_KEY
nano configs/secrets.yaml
# or
open -a TextEdit configs/secrets.yaml
```

#### 7. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

#### 8. Verify Installation

```bash
# Test Python
python3.11 --version
python3.11 -c "import sys; print(sys.version)"

# Test Node.js
node --version
npm --version

# Test Python imports
python3.11 -c "from src.graph_extractor import GraphSchemaExtractor; print('OK')"
```

---

## Post-Installation Configuration

### 1. Configure Environment Variables (Optional)

Create a `.env` file in the project root:

```bash
# .env
OPENAI_API_KEY=sk-...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Test Installation

#### Basic Python Test

```bash
# Activate virtual environment first
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

python scripts/batch_extract.py --help
```

#### Backend Test

```bash
# Activate virtual environment (if needed)
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

# In the project root directory
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# or
python -m backend.src.main
```

Access `http://localhost:8000/docs` to see the API documentation.

#### Frontend Test

```bash
cd frontend
npm run dev
```

Access `http://localhost:3000` in your browser.

---

## Automated Setup Scripts

### Windows

```powershell
# Run setup script
.\scripts\check_setup.ps1
```

### Linux/Mac

```bash
# Create setup script (if needed)
chmod +x scripts/check_setup.sh
./scripts/check_setup.sh
```

---

## Troubleshooting

### Python not found

**Windows:**
- Check if Python is in PATH
- Restart terminal after installing
- Use `py` instead of `python` if necessary

**Linux/Mac:**
- Use `python3.11` explicitly
- Verify with `which python3.11`

### pip not found

```bash
# Windows
python -m ensurepip --upgrade

# Linux/Mac
python3.11 -m ensurepip --upgrade
```

### Compilation errors (Linux/Mac)

```bash
# Install development dependencies
# Ubuntu/Debian
sudo apt install -y build-essential python3-dev

# macOS
xcode-select --install
```

### Node.js not found

**Windows:**
- Restart terminal after installing
- Check PATH in environment variables

**Linux/Mac:**
- Use `nvm` to manage versions
- Verify with `which node`

### Permission errors (Linux/Mac)

```bash
# Don't use sudo with pip/npm when in virtual environment
# If needed, adjust permissions:
sudo chown -R $USER:$USER ~/.npm
```

### Port already in use

```bash
# Backend - use another port (in project root directory)
uvicorn backend.src.main:app --port 8001

# Frontend - use another port
cd frontend
npm run dev -- -p 3001
```

---

## Next Steps

After successful installation:

1. Read the [README.md](README.md) to understand how to use the system
2. Consult the "How to Use the Solution" section in the README
3. Test with sample PDFs in `data/samples/`
4. Configure your `OPENAI_API_KEY` if you want to use LLM fallback
5. 
