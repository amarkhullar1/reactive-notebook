"""FastAPI application with WebSocket endpoint for the reactive notebook."""
import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import (
    Cell, RichOutput, CellUpdatedMessage, ExecuteCellMessage, AddCellMessage, DeleteCellMessage,
    NotebookStateMessage, CellAddedMessage, CellDeletedMessage,
    ExecutionStartedMessage, ExecutionResultMessage, ExecutionQueueMessage, 
    ExecutionInterruptedMessage, ErrorMessage
)
from reactive import ReactiveEngine

app = FastAPI(title="Reactive Notebook")

# Initialize the reactive engine
engine = ReactiveEngine()

# Track current execution state for cancellation
_execution_cancelled: bool = False
_is_executing: bool = False
_execution_task: asyncio.Task | None = None

# Path to notebooks directory
NOTEBOOKS_DIR = Path(__file__).parent.parent / "notebooks"
DEFAULT_NOTEBOOK = NOTEBOOKS_DIR / "default.json"


def ensure_notebooks_dir():
    """Ensure the notebooks directory exists."""
    NOTEBOOKS_DIR.mkdir(exist_ok=True)


def load_notebook():
    """Load notebook from JSON file."""
    ensure_notebooks_dir()
    if DEFAULT_NOTEBOOK.exists():
        try:
            with open(DEFAULT_NOTEBOOK, "r") as f:
                data = json.load(f)
                for cell_data in data.get("cells", []):
                    cell = Cell(**cell_data)
                    engine.add_cell(cell.id, cell.code, position=None)
                    # Restore output/error/status/rich_output
                    if cell.id in engine.cells:
                        engine.cells[cell.id].output = cell.output
                        engine.cells[cell.id].rich_output = cell.rich_output.model_dump() if cell.rich_output else None
                        engine.cells[cell.id].error = cell.error
                        engine.cells[cell.id].status = cell.status
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error loading notebook: {e}")


def save_notebook():
    """Save notebook to JSON file."""
    ensure_notebooks_dir()
    cells_data = [
        {
            "id": cell.id,
            "code": cell.code,
            "output": cell.output,
            "rich_output": cell.rich_output,
            "error": cell.error,
            "status": cell.status
        }
        for cell in engine.get_cells_in_order()
    ]
    with open(DEFAULT_NOTEBOOK, "w") as f:
        json.dump({"cells": cells_data}, f, indent=2)


# Load notebook on startup
load_notebook()


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def send_message(self, websocket: WebSocket, message: dict):
        await websocket.send_json(message)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial notebook state
        cells = engine.get_cells_in_order()
        state_message = NotebookStateMessage(
            cells=[Cell(
                id=c.id,
                code=c.code,
                output=c.output,
                rich_output=RichOutput(**c.rich_output) if c.rich_output else None,
                error=c.error,
                status=c.status
            ) for c in cells]
        )
        await manager.send_message(websocket, state_message.model_dump())
        
        # Listen for messages
        while True:
            data = await websocket.receive_json()
            await handle_message(websocket, data)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def handle_message(websocket: WebSocket, data: dict):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")
    
    if msg_type == "cell_updated":
        await handle_cell_updated(websocket, data)
    elif msg_type == "execute_cell":
        await handle_execute_cell(websocket, data)
    elif msg_type == "add_cell":
        await handle_add_cell(websocket, data)
    elif msg_type == "delete_cell":
        await handle_delete_cell(websocket, data)
    elif msg_type == "interrupt":
        await handle_interrupt(websocket)


async def cancel_current_execution(silent: bool = False):
    """
    Cancel any currently running execution.
    
    Args:
        silent: If True, don't broadcast interruption message
    """
    global _execution_cancelled, _is_executing, _execution_task
    
    if not _is_executing:
        return
    
    # Set flag to cancel execution loop
    _execution_cancelled = True
    
    # Interrupt the kernel (kills worker process)
    interrupt_result = engine.kernel.interrupt()
    
    # Cancel the task if it exists
    if _execution_task and not _execution_task.done():
        _execution_task.cancel()
        try:
            await _execution_task
        except asyncio.CancelledError:
            pass
    
    _is_executing = False
    _execution_task = None
    
    if not silent:
        # Send interrupted message
        interrupted_msg = ExecutionInterruptedMessage(
            cell_id=interrupt_result.get("cell_id"),
            message="Execution interrupted"
        )
        await manager.broadcast(interrupted_msg.model_dump())


async def run_execution(execution_order: list[str]):
    """
    Background task to execute cells in order.
    
    This runs as a separate task so the WebSocket can continue
    receiving messages (like interrupt) during execution.
    """
    global _execution_cancelled, _is_executing
    
    try:
        # Send execution queue
        queue_msg = ExecutionQueueMessage(cell_ids=execution_order)
        await manager.broadcast(queue_msg.model_dump())
        
        # Execute cells in order
        for exec_cell_id in execution_order:
            # Check if cancelled
            if _execution_cancelled:
                # Mark remaining cells as idle and send updates
                for remaining_id in execution_order[execution_order.index(exec_cell_id):]:
                    if remaining_id in engine.cells:
                        engine.cells[remaining_id].status = "idle"
                break
            
            # Check if cell still exists (might have been deleted)
            if exec_cell_id not in engine.cells:
                continue
            
            # Send execution started
            started_msg = ExecutionStartedMessage(cell_id=exec_cell_id)
            await manager.broadcast(started_msg.model_dump())
            
            # Execute cell in a thread to not block the event loop
            exec_result = await asyncio.to_thread(engine.execute_cell, exec_cell_id)
            
            # Check if interrupted during execution
            if _execution_cancelled:
                # Send interrupted message for this cell
                interrupted_msg = ExecutionInterruptedMessage(
                    cell_id=exec_cell_id,
                    message="Execution interrupted"
                )
                await manager.broadcast(interrupted_msg.model_dump())
                break
            
            # Build rich_output model if present
            rich_output = None
            if exec_result.get("rich_output"):
                rich_output = RichOutput(**exec_result["rich_output"])
            
            # Send execution result
            result_msg = ExecutionResultMessage(
                cell_id=exec_cell_id,
                status=exec_result["status"],
                output=exec_result["output"],
                rich_output=rich_output,
                error=exec_result["error"]
            )
            await manager.broadcast(result_msg.model_dump())
    
    except asyncio.CancelledError:
        # Task was cancelled - this is expected during interrupt
        pass
    
    finally:
        _is_executing = False
        save_notebook()


async def handle_cell_updated(websocket: WebSocket, data: dict):
    """Handle cell code update and trigger reactive execution."""
    global _execution_cancelled, _is_executing, _execution_task
    
    cell_id = data["cell_id"]
    code = data["code"]
    
    # Cancel any running execution first (cancel-and-replace)
    if _is_executing:
        await cancel_current_execution(silent=True)
    
    # Update cell and get execution plan
    result = engine.on_cell_changed(cell_id, code)
    
    if result.get("error"):
        # Send error (e.g., circular dependency)
        error_msg = ErrorMessage(cell_id=cell_id, message=result["error"])
        await manager.broadcast(error_msg.model_dump())
        save_notebook()
        return
    
    execution_order = result.get("execution_order", [])
    
    if execution_order:
        # Reset cancellation flag and mark as executing
        _execution_cancelled = False
        _is_executing = True
        
        # Start execution as a background task - don't await it!
        # This allows the WebSocket to continue receiving messages (like interrupt)
        _execution_task = asyncio.create_task(run_execution(execution_order))
    else:
        save_notebook()


async def handle_execute_cell(websocket: WebSocket, data: dict):
    """Handle manual cell execution request."""
    cell_id = data["cell_id"]
    
    if cell_id not in engine.cells:
        return
    
    # Get the cell's current code and trigger update
    code = engine.cells[cell_id].code
    await handle_cell_updated(websocket, {"cell_id": cell_id, "code": code})


async def handle_add_cell(websocket: WebSocket, data: dict):
    """Handle add cell request."""
    position = data.get("position")
    
    cell = engine.add_cell(position=position)
    
    added_msg = CellAddedMessage(
        cell=Cell(
            id=cell.id,
            code=cell.code,
            output=cell.output,
            rich_output=None,
            error=cell.error,
            status=cell.status
        ),
        position=position if position is not None else len(engine.cell_order) - 1
    )
    await manager.broadcast(added_msg.model_dump())
    save_notebook()


async def handle_delete_cell(websocket: WebSocket, data: dict):
    """Handle delete cell request."""
    cell_id = data["cell_id"]
    
    # If the cell being deleted is currently running, interrupt first
    if _is_executing and engine.kernel.current_cell == cell_id:
        await cancel_current_execution(silent=True)
    
    if engine.delete_cell(cell_id):
        deleted_msg = CellDeletedMessage(cell_id=cell_id)
        await manager.broadcast(deleted_msg.model_dump())
        save_notebook()


async def handle_interrupt(websocket: WebSocket):
    """Handle interrupt request - stops current execution."""
    await cancel_current_execution(silent=False)
    save_notebook()


# Serve static files in production
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_BUILD_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_BUILD_DIR / "assets"), name="assets")
    
    @app.get("/")
    async def serve_frontend():
        return FileResponse(FRONTEND_BUILD_DIR / "index.html")
    
    @app.get("/{path:path}")
    async def serve_frontend_paths(path: str):
        file_path = FRONTEND_BUILD_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_BUILD_DIR / "index.html")

