# Reactive Notebook

A minimal reactive Python notebook where editing a cell automatically re-runs dependent cells.

## Features

- **Reactive Execution**: Edit any cell and watch dependent cells automatically re-run
- **Live Feedback**: See execution status (idle/running/success/error) for each cell
- **Dependency Detection**: Automatic detection of variable dependencies between cells
- **Monaco Editor**: Full-featured Python code editing with syntax highlighting
- **Persistence**: Notebook state is saved to disk and restored on restart

## Quick Start

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r ../requirements.txt
uvicorn main:app --reload
```

### Frontend Setup (Development)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open your browser to http://localhost:5173

### Production Mode

Build the frontend and run from a single server:

```bash
cd frontend
npm run build

cd ../backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open your browser to http://localhost:8000

## Architecture

- **Backend**: Python + FastAPI with WebSocket for real-time communication
- **Frontend**: React + TypeScript + Monaco Editor
- **Dependency Detection**: Python AST analysis
- **Execution**: Direct `exec()` in shared namespace

## How It Works

1. When you edit a cell, the frontend debounces and sends the update to the backend
2. The backend analyzes dependencies using Python's AST module
3. It finds all downstream cells that depend on variables defined in the changed cell
4. It topologically sorts the affected cells and executes them in order
5. Results are streamed back to the frontend in real-time

## Keyboard Shortcuts

- `Shift + Enter`: Run the current cell
- `Cmd/Ctrl + Enter`: Add a new cell

## Limitations (MVP)

- Single user only
- No authentication
- No timeout handling (infinite loops will hang the server)
- No sandbox (runs with full Python access)
- Text-only output (no images or HTML)

