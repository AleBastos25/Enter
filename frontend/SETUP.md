# Frontend Setup - Graph Extractor UI

## Warning

**Installation Validation:**
- ✅ **Windows**: Instructions validated and tested on the developer's machine
- ⚠️ **Linux and macOS**: Instructions based on documentation and AI assistance (GPT-5). **Not tested in a real environment**. If you encounter issues, please report or adjust according to your distribution/operating system version.

## ⚠️ Node.js Required

The frontend requires **Node.js 18+** and **npm** (comes with Node.js).

## Node.js Installation

### Windows

1. **Download Node.js LTS**:
   - Visit: https://nodejs.org/
   - Download the LTS (recommended) version
   - Run the `.msi` installer

2. **During installation**:
   - ✅ Check "Add to PATH"
   - ✅ Check "Automatically install necessary tools"

3. **Restart PowerShell/Terminal**

4. **Verify installation**:
   ```powershell
   node --version
   npm --version
   ```

**Alternatives:**

- **Chocolatey:**
  ```powershell
  choco install nodejs-lts
  ```

- **winget:**
  ```powershell
  winget install OpenJS.NodeJS.LTS
  ```

### Linux (Ubuntu/Debian)

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

**Option C: Snap**

```bash
sudo snap install node --classic
```

### macOS

**Option A: Homebrew (Recommended)**

```bash
# Install Node.js LTS via Homebrew
brew install node@20

# Verify
node --version
npm --version
```

**Option B: nvm**

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

**Option C: Official Installer**

1. Download from https://nodejs.org/
2. Run the `.pkg` installer
3. Follow the installer instructions

## Dependency Installation

After installing Node.js:

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

This will install:
- Next.js
- React
- TypeScript
- TailwindCSS
- Axios
- JSZip

## Execution

**Windows:**
```powershell
# Development
npm run dev

# Production build
npm run build

# Run production
npm start
```

**Linux/Mac:**
```bash
# Development
npm run dev

# Production build
npm run build

# Run production
npm start
```

## Configuration

Create a `.env.local` file (optional):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If the backend is on another port, adjust as needed.

## Common Problems

### "npm is not recognized"

- Node.js is not installed
- Node.js is not in PATH
- Restart terminal after installing

### Module not found error

**Windows:**
```powershell
# Clear cache and reinstall
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
```

**Linux/Mac:**
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Port 3000 occupied

**Windows:**
```powershell
npm run dev -- -p 3001
```

**Linux/Mac:**
```bash
npm run dev -- -p 3001
```

### Permission problems (Linux/Mac)

```bash
# Adjust npm permissions
sudo chown -R $USER:$USER ~/.npm
```
