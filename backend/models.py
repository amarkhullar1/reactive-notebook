"""Pydantic models for WebSocket message types."""
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


# Frontend → Backend Messages

class CellUpdatedMessage(BaseModel):
    """User edited a cell."""
    type: Literal["cell_updated"] = "cell_updated"
    cell_id: str
    code: str


class ExecuteCellMessage(BaseModel):
    """User manually triggered execution."""
    type: Literal["execute_cell"] = "execute_cell"
    cell_id: str


class AddCellMessage(BaseModel):
    """User wants to add a new cell."""
    type: Literal["add_cell"] = "add_cell"
    position: int


class DeleteCellMessage(BaseModel):
    """User wants to delete a cell."""
    type: Literal["delete_cell"] = "delete_cell"
    cell_id: str


class InterruptMessage(BaseModel):
    """User wants to interrupt execution."""
    type: Literal["interrupt"] = "interrupt"


# Backend → Frontend Messages

class NotebookStateMessage(BaseModel):
    """Initial state when client connects."""
    type: Literal["notebook_state"] = "notebook_state"
    cells: list[Cell]


class CellAddedMessage(BaseModel):
    """Cell added confirmation."""
    type: Literal["cell_added"] = "cell_added"
    cell: Cell
    position: int


class CellDeletedMessage(BaseModel):
    """Cell deleted confirmation."""
    type: Literal["cell_deleted"] = "cell_deleted"
    cell_id: str


class ExecutionStartedMessage(BaseModel):
    """Cell execution started."""
    type: Literal["execution_started"] = "execution_started"
    cell_id: str


class ExecutionResultMessage(BaseModel):
    """Cell execution completed."""
    type: Literal["execution_result"] = "execution_result"
    cell_id: str
    status: CellStatus
    output: str
    rich_output: Optional[RichOutput] = None
    error: str


class ExecutionQueueMessage(BaseModel):
    """Multiple cells queued for execution."""
    type: Literal["execution_queue"] = "execution_queue"
    cell_ids: list[str]


class ExecutionInterruptedMessage(BaseModel):
    """Execution was interrupted by user."""
    type: Literal["execution_interrupted"] = "execution_interrupted"
    cell_id: Optional[str] = None
    message: str = "Execution interrupted"


class ErrorMessage(BaseModel):
    """Error message (e.g., circular dependency)."""
    type: Literal["error"] = "error"
    cell_id: Optional[str] = None
    message: str

