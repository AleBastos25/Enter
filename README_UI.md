# UI Graph Extractor - Documentation

Complete interface for extracting data from PDFs using Graph Extractor.

## Structure

- **Backend**: FastAPI in `backend/`
- **Frontend**: Next.js/React in `frontend/`

## Prerequisites

- **Python 3.10+** (for backend)
- **Node.js 18+** and **npm** (for frontend)

> ⚠️ **Important**: If you get an error "npm is not recognized", you need to install Node.js first.
> See [INSTALLATION.md](INSTALLATION.md) or [frontend/SETUP.md](frontend/SETUP.md) for detailed instructions.

## 🚀 Quick Start

**Easiest method**: Run `start-ui.bat` (double-click) or `.\start-ui.ps1` in PowerShell.

The script automatically:
- Configures Node.js
- Starts the backend
- Starts the frontend  
- Opens the browser

See [START_UI.md](START_UI.md) for more details.

## Manual Installation and Execution

### 1. Install Node.js (if you don't have it yet)

**Windows:**
- Download from: https://nodejs.org/ (LTS version)
- Option A: Run the `.msi` installer (recommended - adds to PATH automatically)
- Option B: Extract the zip and add to PATH manually

**If you already downloaded Node.js (e.g., `C:\Users\aleba\Downloads\node-v24.11.0-win-x64`):**
```powershell
# Run the setup script
.\setup_node_path.ps1

# Or add manually to PATH:
[Environment]::SetEnvironmentVariable("Path", "$([Environment]::GetEnvironmentVariable('Path','User'));C:\Users\aleba\Downloads\node-v24.11.0-win-x64", "User")
```

Restart terminal and verify: `node --version` and `npm --version`

### 2. Backend

```bash
# In the project root directory
# Install dependencies (if not already installed)
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Run server
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# or
python -m backend.src.main
```

The backend will be available at `http://localhost:8000`.

**Note for Windows:** You can use the `start-ui.bat` script (double-click) or `.\start-ui.ps1` in PowerShell to automatically start the backend and frontend. The `start-ui.bat` script can be adapted to run on any Windows machine.

### 3. Frontend

```bash
# Install dependencies (after installing Node.js)
cd frontend
npm install

# Run in development
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Implemented Features

### Backend

- ✅ `POST /api/graph-extract` endpoint for extracting multiple PDFs
- ✅ `GET /graph/{run_id}.html` endpoint for graph visualization
- ✅ Support for progress callbacks in Graph Extractor
- ✅ Graph HTML generation during extraction (dev mode)
- ✅ Validation of up to 10 PDFs per request
- ✅ Sequential PDF processing
- ✅ Extraction of used rules from metadata

### Frontend

- ✅ ChatGPT-style interface
- ✅ JSON schema upload (file or manual)
- ✅ PDF Drag & Drop (up to 10)
- ✅ Recent labels autocomplete
- ✅ Real-time result visualization
- ✅ Dev mode with graph visualization, time and rules
- ✅ Sidebar with pages and search
- ✅ Organization by folders (labels)
- ✅ Session persistence (sessionStorage)
- ✅ Copy and Download JSON buttons
- ✅ Retry per run (structure ready)

## Usage

1. **Start Backend**: Run the FastAPI server on port 8000
2. **Start Frontend**: Run the Next.js server on port 3000
3. **Access UI**: Open `http://localhost:3000` in your browser
4. **Extract Data**:
   - Enter a label
   - Upload a JSON schema or write manually
   - Add PDFs (drag & drop or selection)
   - Click "Send"
   - Wait for sequential processing
   - View results

## Dev Mode

Activate the "Dev Mode" toggle in the header to:
- See processing time
- See rules/strategies used
- Access "Open Graph" link for HTML graph visualization

## Notes

- Persistence is only in session (lost when closing tab)
- Dev mode persists in localStorage
- Graph HTMLs are generated only in dev mode
- Processing is sequential (one PDF at a time)

## Next Steps (Optional)

- [ ] Implement real-time streaming with SSE
- [ ] Add ZIP export of inputs/outputs
- [ ] Improve error handling
- [ ] Add more robust schema validation
- [ ] Implement complete retry
- [ ] Add more detailed loading states
