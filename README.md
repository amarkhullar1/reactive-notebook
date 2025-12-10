# Reactive Notebook

A reactive Python notebook with **Excel-style dependency tracking** where cells can depend on any other cell regardless of vertical position.

## Features

- **Excel-Style Reactive Execution**: Cells can depend on ANY other cell, not just cells above them
- **Automatic Dependency Detection**: Uses Python AST to detect variable definitions and usages
- **Topological Execution Order**: Cells execute in dependency order, not display order
- **Live Feedback**: See execution status (idle/running/success/error) for each cell
- **Cycle Detection**: Circular dependencies are detected and reported
- **Monaco Editor**: Full-featured Python code editing with syntax highlighting
- **Multiple Notebooks**: Create, switch between, rename, and delete notebooks - each with its own isolated namespace
- **Persistence**: Notebooks are saved to disk and restored on restart
- **Rich Output Display**: Beautiful rendering of pandas DataFrames, Series, and numpy arrays

## How It Differs from Jupyter

| Feature | Jupyter | Reactive Notebook |
|---------|---------|-------------------|
| Dependencies | Cells only see variables from cells executed above | Cells can depend on any other cell |
| Execution | Manual, in any order | Automatic, respects dependency DAG |
| Variable Scope | Based on execution order | Based on symbol definitions |

### Example

```
Cell 1: result = x + y    # Depends on x, y from cells below
Cell 2: x = 10
Cell 3: y = 20
```

In **Jupyter**: Cell 1 would fail (x, y not defined)
In **Reactive Notebook**: Execution order is Cell 2 → Cell 3 → Cell 1, result = 30 ✓

## Quick Start

### Using Make (Recommended)

```bash
# Install all dependencies
make install

# Run in development mode (backend + frontend)
make dev

# Run tests
make test

# See all available commands
make help
```

### Manual Setup

#### Backend Setup

```bash
cd backend
python3 -m venv ../venv
source ../venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r ../requirements.txt
uvicorn main:app --reload
```

#### Frontend Setup (Development)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open your browser to http://localhost:5173

### Production Mode

```bash
make prod
# Or manually:
cd frontend && npm run build
cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

Open your browser to http://localhost:8000

## Architecture

- **Backend**: Python + FastAPI with WebSocket for real-time communication
- **Frontend**: React + TypeScript + Monaco Editor
- **Dependency Detection**: Python AST analysis (order-independent)
- **Execution**: Direct `exec()` in shared namespace

## How It Works

1. When you edit a cell, the frontend debounces and sends the update to the backend
2. The backend analyzes dependencies using Python's AST module
3. It builds an order-independent dependency DAG based on symbol definitions/usages
4. It finds all transitively dependent cells (which can be above or below)
5. It topologically sorts affected cells and executes them in dependency order
6. Results are streamed back to the frontend in real-time

## Keyboard Shortcuts

- `Shift + Enter`: Run the current cell
- `Cmd/Ctrl + Enter`: Add a new cell

## Testing

```bash
# Run all tests
make test

# Run tests in watch mode
make test-watch

# Run tests directly with pytest
cd backend && python -m pytest -v
```

### Test Coverage

- **144 tests** covering:
  - Variable definition detection (assignments, functions, classes, imports)
  - Variable usage detection
  - Dependency graph construction (Excel-style)
  - Downstream cell detection
  - Topological sorting
  - Cycle detection
  - Kernel execution (success, errors, output capture)
  - Reactive engine (cell management, execution flow)
  - Rich output serialization (DataFrames, Series, ndarrays)
  - Notebook management (create, delete, rename, persistence, isolated namespaces)

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies |
| `make dev` | Start both backend and frontend in dev mode |
| `make dev-backend` | Start backend only with hot reload |
| `make dev-frontend` | Start frontend only (Vite) |
| `make build` | Build frontend for production |
| `make prod` | Build and start in production mode |
| `make start` | Start production server |
| `make stop` | Stop all running servers |
| `make restart` | Restart the application |
| `make test` | Run all tests |
| `make clean` | Remove build artifacts |

## Limitations (MVP)

- Single user only
- No authentication

- No sandbox (runs with full Python access)
- No image output (matplotlib plots, etc.)

