"""Pydantic models for WebSocket message types."""
from datetime import datetime
from typing import Literal, Optional, Any
from pydantic import BaseModel


# Cell status type
CellStatus = Literal["idle", "running", "success", "error"]

# Rich output types
RichOutputType = Literal["dataframe", "series", "ndarray"]


class RichOutput(BaseModel):
    """Structured output for DataFrames, Series, and arrays."""
    type: RichOutputType
    data: Any  # The actual data (list of records for DataFrame, etc.)
    columns: Optional[list[str]] = None  # Column names for DataFrame
    dtypes: Optional[dict[str, str]] = None  # Data types per column
    index: Optional[list[Any]] = None  # Index values
    name: Optional[str] = None  # Series name
    shape: list[int]  # Shape of the data
    truncated: bool = False  # Whether data was truncated


class Cell(BaseModel):
    """Represents a notebook cell."""
    id: str
    code: str = ""
    output: str = ""
    rich_output: Optional[RichOutput] = None  # Structured output for DataFrames etc.
    error: str = ""
    status: CellStatus = "idle"


class NotebookMetadata(BaseModel):
    """Metadata for a notebook (used in listing)."""
    id: str
    name: str
    created_at: str  # ISO format datetime string
    updated_at: str  # ISO format datetime string


# Frontend → Backend Messages

class CellUpdatedMessage(BaseModel):
    """User edited a cell."""
    type: Literal["cell_updated"] = "cell_updated"
    notebook_id: str
    cell_id: str
    code: str


class ExecuteCellMessage(BaseModel):
    """User manually triggered execution."""
    type: Literal["execute_cell"] = "execute_cell"
    notebook_id: str
    cell_id: str


class AddCellMessage(BaseModel):
    """User wants to add a new cell."""
    type: Literal["add_cell"] = "add_cell"
    notebook_id: str
    position: int


class DeleteCellMessage(BaseModel):
    """User wants to delete a cell."""
    type: Literal["delete_cell"] = "delete_cell"
    notebook_id: str
    cell_id: str


class InterruptMessage(BaseModel):
    """User wants to interrupt execution."""
    type: Literal["interrupt"] = "interrupt"
    notebook_id: str


# Notebook management messages (Frontend → Backend)

class ListNotebooksMessage(BaseModel):
    """Request list of all notebooks."""
    type: Literal["list_notebooks"] = "list_notebooks"


class CreateNotebookMessage(BaseModel):
    """Create a new notebook."""
    type: Literal["create_notebook"] = "create_notebook"
    name: str


class DeleteNotebookMessage(BaseModel):
    """Delete a notebook."""
    type: Literal["delete_notebook"] = "delete_notebook"
    notebook_id: str


class RenameNotebookMessage(BaseModel):
    """Rename a notebook."""
    type: Literal["rename_notebook"] = "rename_notebook"
    notebook_id: str
    name: str


class OpenNotebookMessage(BaseModel):
    """Open/switch to a notebook."""
    type: Literal["open_notebook"] = "open_notebook"
    notebook_id: str


# Backend → Frontend Messages

class NotebookStateMessage(BaseModel):
    """State of the currently open notebook."""
    type: Literal["notebook_state"] = "notebook_state"
    notebook_id: str
    notebook_name: str
    cells: list[Cell]


class NotebooksListMessage(BaseModel):
    """List of all available notebooks."""
    type: Literal["notebooks_list"] = "notebooks_list"
    notebooks: list[NotebookMetadata]
    active_notebook_id: Optional[str] = None


class NotebookCreatedMessage(BaseModel):
    """Confirmation that a notebook was created."""
    type: Literal["notebook_created"] = "notebook_created"
    notebook: NotebookMetadata


class NotebookDeletedMessage(BaseModel):
    """Confirmation that a notebook was deleted."""
    type: Literal["notebook_deleted"] = "notebook_deleted"
    notebook_id: str


class NotebookRenamedMessage(BaseModel):
    """Confirmation that a notebook was renamed."""
    type: Literal["notebook_renamed"] = "notebook_renamed"
    notebook_id: str
    name: str


class CellAddedMessage(BaseModel):
    """Cell added confirmation."""
    type: Literal["cell_added"] = "cell_added"
    notebook_id: str
    cell: Cell
    position: int


class CellDeletedMessage(BaseModel):
    """Cell deleted confirmation."""
    type: Literal["cell_deleted"] = "cell_deleted"
    notebook_id: str
    cell_id: str


class ExecutionStartedMessage(BaseModel):
    """Cell execution started."""
    type: Literal["execution_started"] = "execution_started"
    notebook_id: str
    cell_id: str


class ExecutionResultMessage(BaseModel):
    """Cell execution completed."""
    type: Literal["execution_result"] = "execution_result"
    notebook_id: str
    cell_id: str
    status: CellStatus
    output: str
    rich_output: Optional[RichOutput] = None
    error: str


class ExecutionQueueMessage(BaseModel):
    """Multiple cells queued for execution."""
    type: Literal["execution_queue"] = "execution_queue"
    notebook_id: str
    cell_ids: list[str]


class ExecutionInterruptedMessage(BaseModel):
    """Execution was interrupted by user."""
    type: Literal["execution_interrupted"] = "execution_interrupted"
    notebook_id: str
    cell_id: Optional[str] = None
    message: str = "Execution interrupted"


class ErrorMessage(BaseModel):
    """Error message (e.g., circular dependency)."""
    type: Literal["error"] = "error"
    notebook_id: Optional[str] = None
    cell_id: Optional[str] = None
    message: str

