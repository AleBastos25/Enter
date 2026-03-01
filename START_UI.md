# How to Start the UI

## Method 1: Double-click (easiest)

1. Double-click the `start-ui.bat` file
2. The script will automatically start the backend and frontend

## Method 2: PowerShell

1. Open PowerShell in the project root
2. Run:
   ```powershell
   .\start-ui.ps1
   ```

## What the script does:

1. ✅ Finds and configures Node.js
2. ✅ Checks if backend is running (port 8000)
3. ✅ Starts backend in a new window (if needed)
4. ✅ Checks if frontend is running (port 3000)
5. ✅ Installs frontend dependencies (if needed)
6. ✅ Starts frontend
7. ✅ Automatically opens browser at http://localhost:3000

## Requirements:

- Python 3.10+ installed
- Node.js installed (script searches in common locations)
- Python virtual environment created (`.venv`) - optional

## Common problems:

### Execution policy error

If you get an error about execution policy, run in PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Backend doesn't start

Check if port 8000 is free:

```powershell
netstat -ano | findstr :8000
```

### Frontend doesn't start

Check if port 3000 is free:

```powershell
netstat -ano | findstr :3000
```

## Stop the application:

- **Frontend**: Press `Ctrl+C` in the frontend terminal
- **Backend**: Close the PowerShell window of the backend or press `Ctrl+C`

## URLs:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

