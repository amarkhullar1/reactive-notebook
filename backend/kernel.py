"""Code execution engine for the reactive notebook using a worker process."""
import ast
import sys
import math
import multiprocessing
from multiprocessing import Process, Queue
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Optional
from queue import Empty

# Try to import data science libraries
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None


# Maximum rows/elements to include in rich output
MAX_ROWS = 100
MAX_ARRAY_ELEMENTS = 1000


def _safe_value(val: Any) -> Any:
    """Convert a value to a JSON-safe representation."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val):
            return "NaN"
        if math.isinf(val):
            return "Infinity" if val > 0 else "-Infinity"
    if HAS_NUMPY and isinstance(val, (np.integer, np.floating)):
        return _safe_value(val.item())
    if HAS_NUMPY and isinstance(val, np.bool_):
        return bool(val)
    if HAS_PANDAS and pd.isna(val):
        return None
    return val


def _convert_to_safe_list(data: list) -> list:
    """Recursively convert list values to JSON-safe format."""
    result = []
    for item in data:
        if isinstance(item, list):
            result.append(_convert_to_safe_list(item))
        elif isinstance(item, dict):
            result.append({k: _safe_value(v) for k, v in item.items()})
        else:
            result.append(_safe_value(item))
    return result


def serialize_rich_output(value: Any) -> Optional[dict]:
    """
    Convert special data types to structured output for rich rendering.
    
    Supports:
    - pandas DataFrame
    - pandas Series
    - numpy ndarray
    
    Returns:
        Dict with type, data, shape, etc. or None if not a rich type.
    """
    if value is None:
        return None
    
    # Check for pandas DataFrame
    if HAS_PANDAS and isinstance(value, pd.DataFrame):
        truncated = len(value) > MAX_ROWS
        df_display = value.head(MAX_ROWS) if truncated else value
        
        # Convert to records and handle NaN/special values
        records = df_display.to_dict(orient="records")
        safe_records = _convert_to_safe_list(records)
        
        # Get index as list
        index_list = [_safe_value(idx) for idx in df_display.index.tolist()]
        
        return {
            "type": "dataframe",
            "data": safe_records,
            "columns": list(df_display.columns),
            "dtypes": {str(col): str(dtype) for col, dtype in value.dtypes.items()},
            "index": index_list,
            "shape": list(value.shape),
            "truncated": truncated
        }
    
    # Check for pandas Series
    if HAS_PANDAS and isinstance(value, pd.Series):
        truncated = len(value) > MAX_ROWS
        series_display = value.head(MAX_ROWS) if truncated else value
        
        # Convert to dict with safe values
        data_dict = {_safe_value(k): _safe_value(v) for k, v in series_display.to_dict().items()}
        
        return {
            "type": "series",
            "data": data_dict,
            "name": value.name,
            "dtype": str(value.dtype),
            "index": [_safe_value(idx) for idx in series_display.index.tolist()],
            "shape": [len(value)],
            "truncated": truncated
        }
    
    # Check for numpy ndarray
    if HAS_NUMPY and isinstance(value, np.ndarray):
        total_elements = value.size
        truncated = total_elements > MAX_ARRAY_ELEMENTS
        
        if value.ndim == 1:
            # 1D array - take first MAX_ARRAY_ELEMENTS
            arr_display = value[:MAX_ARRAY_ELEMENTS] if truncated else value
            data = _convert_to_safe_list(arr_display.tolist())
        elif value.ndim == 2:
            # 2D array - limit rows and columns
            max_dim = int(MAX_ARRAY_ELEMENTS ** 0.5)  # ~31 for 1000
            row_limit = min(value.shape[0], max_dim)
            col_limit = min(value.shape[1], max_dim)
            arr_display = value[:row_limit, :col_limit]
            truncated = value.shape[0] > row_limit or value.shape[1] > col_limit
            data = _convert_to_safe_list(arr_display.tolist())
        else:
            # Higher dimensional - just show shape and flatten preview
            flat = value.flatten()[:MAX_ARRAY_ELEMENTS]
            data = _convert_to_safe_list(flat.tolist())
            truncated = total_elements > MAX_ARRAY_ELEMENTS
        
        return {
            "type": "ndarray",
            "data": data,
            "dtype": str(value.dtype),
            "shape": list(value.shape),
            "truncated": truncated
        }
    
    return None


# Default timeout in seconds
DEFAULT_TIMEOUT = 5


# Command types for worker communication
CMD_EXECUTE = "execute"
CMD_GET_VAR = "get_var"
CMD_SET_VAR = "set_var"
CMD_RESET = "reset"
CMD_SHUTDOWN = "shutdown"

# Sentinel value to signal interrupt
INTERRUPTED_SENTINEL = {"__interrupted__": True}


def _execute_code(code: str, namespace: dict) -> dict:
    """
    Execute Python code in the given namespace.
    
    Returns:
        Dict with status, output, error, and optional result_value
    """
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    result_value = None
    
    try:
        # Parse the code
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "error",
                "output": "",
                "error": f"SyntaxError: {e.msg} (line {e.lineno})",
                "result_value": None
            }
        
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                # Last statement is an expression - eval it to capture value
                # Execute all but the last statement
                if len(tree.body) > 1:
                    module = ast.Module(body=tree.body[:-1], type_ignores=[])
                    exec(compile(module, '<cell>', 'exec'), namespace)
                
                # Eval the last expression
                last_expr = ast.Expression(body=tree.body[-1].value)
                result_value = eval(compile(last_expr, '<cell>', 'eval'), namespace)
            else:
                # No trailing expression, just exec everything
                exec(compile(tree, '<cell>', 'exec'), namespace)
        
        # Build output: stdout + repr of last expression (if any)
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        
        output_parts = []
        if stdout_output:
            output_parts.append(stdout_output.rstrip())
        if result_value is not None:
            output_parts.append(repr(result_value))
        
        output = '\n'.join(output_parts)
        
        return {
            "status": "success",
            "output": output,
            "error": stderr_output,
            "result_value": result_value
        }
    
    except Exception as e:
        return {
            "status": "error",
            "output": stdout_capture.getvalue(),
            "error": f"{type(e).__name__}: {str(e)}",
            "result_value": None
        }


def _worker_loop(request_queue: Queue, response_queue: Queue):
    """
    Worker process main loop.
    
    Receives commands from request_queue, executes them, and sends
    results to response_queue. Maintains a persistent namespace.
    """
    namespace: dict[str, Any] = {}
    
    while True:
        try:
            # Wait for a command
            cmd = request_queue.get()
            
            if cmd is None or cmd.get("type") == CMD_SHUTDOWN:
                break
            
            cmd_type = cmd.get("type")
            
            if cmd_type == CMD_EXECUTE:
                code = cmd.get("code", "")
                if not code.strip():
                    result = {
                        "status": "success",
                        "output": "",
                        "error": ""
                    }
                else:
                    result = _execute_code(code, namespace)
                    # Remove result_value from response (not serializable for complex objects)
                    result.pop("result_value", None)
                response_queue.put(result)
            
            elif cmd_type == CMD_GET_VAR:
                name = cmd.get("name")
                value = namespace.get(name)
                # Try to send the value; if not picklable, send None
                try:
                    response_queue.put({"value": value})
                except Exception:
                    response_queue.put({"value": None, "error": "Value not serializable"})
            
            elif cmd_type == CMD_SET_VAR:
                name = cmd.get("name")
                value = cmd.get("value")
                namespace[name] = value
                response_queue.put({"status": "ok"})
            
            elif cmd_type == CMD_RESET:
                namespace.clear()
                response_queue.put({"status": "ok"})
        
        except Exception as e:
            # Send error back
            try:
                response_queue.put({
                    "status": "error",
                    "output": "",
                    "error": f"Worker error: {type(e).__name__}: {str(e)}"
                })
            except Exception:
                pass  # Queue might be broken


class NotebookKernel:
    """
    Executes Python code in a separate worker process.
    
    Features:
    - Persistent namespace across cell executions (in worker process)
    - Non-blocking: main process stays responsive during execution
    - True timeout: worker can be killed if it hangs
    - Interruptible: can cancel running execution
    - Captures stdout and stderr
    - Returns the value of the last expression (like Jupyter)
    """
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.cell_outputs: dict[str, dict] = {}
        
        # Worker process and communication queues
        self._request_queue: Optional[Queue] = None
        self._response_queue: Optional[Queue] = None
        self._worker: Optional[Process] = None
        
        # Track if execution is in progress
        self._executing: bool = False
        self._current_cell_id: Optional[str] = None
        
        # Start the worker
        self._start_worker()
    
    def _start_worker(self):
        """Start or restart the worker process."""
        # Clean up existing worker if any
        self._stop_worker()
        
        # Create new queues and worker
        self._request_queue = Queue()
        self._response_queue = Queue()
        self._worker = Process(
            target=_worker_loop,
            args=(self._request_queue, self._response_queue),
            daemon=True
        )
        self._worker.start()
    
    def _stop_worker(self):
        """Stop the worker process."""
        if self._worker is not None and self._worker.is_alive():
            # Try graceful shutdown first
            try:
                self._request_queue.put({"type": CMD_SHUTDOWN})
                self._worker.join(timeout=1)
            except Exception:
                pass
            
            # Force terminate if still alive
            if self._worker.is_alive():
                self._worker.terminate()
                self._worker.join(timeout=1)
                
                # Last resort: kill
                if self._worker.is_alive():
                    self._worker.kill()
                    self._worker.join(timeout=1)
        
        self._worker = None
        self._request_queue = None
        self._response_queue = None
    
    def _ensure_worker(self):
        """Ensure the worker process is running."""
        if self._worker is None or not self._worker.is_alive():
            self._start_worker()
    
    def reset(self):
        """Reset the kernel namespace."""
        self._ensure_worker()
        self.cell_outputs.clear()
        
        try:
            self._request_queue.put({"type": CMD_RESET})
            self._response_queue.get(timeout=5)
        except Exception:
            # If reset fails, restart the worker
            self._start_worker()
    
    @property
    def is_busy(self) -> bool:
        """Check if the kernel is currently executing code."""
        return self._executing
    
    @property
    def current_cell(self) -> Optional[str]:
        """Get the ID of the currently executing cell, if any."""
        return self._current_cell_id
    
    def interrupt(self) -> dict:
        """
        Interrupt the currently running execution.
        
        Kills the worker process and restarts it. Any running code is terminated.
        
        Returns:
            Dict with status information
        """
        cell_id = self._current_cell_id
        was_executing = self._executing
        
        # Put interrupt sentinel on the old response queue to unblock any waiting threads
        # This must happen BEFORE we restart the worker (which creates new queues)
        if self._response_queue is not None:
            try:
                self._response_queue.put(INTERRUPTED_SENTINEL)
            except Exception:
                pass  # Queue might be broken
        
        # Restart the worker (this kills any running code)
        self._start_worker()
        self._executing = False
        self._current_cell_id = None
        
        if was_executing:
            return {
                "status": "interrupted",
                "cell_id": cell_id,
                "message": "Execution interrupted by user"
            }
        return {
            "status": "ok",
            "message": "No execution was running"
        }
    
    def execute_cell(
        self, 
        cell_id: str, 
        code: str,
        timeout: Optional[int] = None
    ) -> dict:
        """
        Execute Python code and capture output.
        
        Args:
            cell_id: Unique identifier for the cell
            code: Python code to execute
            timeout: Optional timeout in seconds (defaults to kernel timeout)
        
        Returns:
            Dict with keys:
            - status: "success" or "error"
            - output: Combined stdout and last expression value
            - error: Error message if any
        """
        self._ensure_worker()
        
        if not code.strip():
            result = {
                "status": "success",
                "output": "",
                "rich_output": None,
                "error": ""
            }
            self.cell_outputs[cell_id] = result
            return result
        
        effective_timeout = timeout if timeout is not None else self.timeout
        
        # Track execution state
        self._executing = True
        self._current_cell_id = cell_id
        
        try:
            # Send execution request to worker
            self._request_queue.put({
                "type": CMD_EXECUTE,
                "code": code
            })
            
            # Wait for response with timeout
            try:
                result = self._response_queue.get(timeout=effective_timeout)
                
                # Check if this is an interrupt sentinel
                if isinstance(result, dict) and result.get("__interrupted__"):
                    result = {
                        "status": "error",
                        "output": "",
                        "error": "Interrupted"
                    }
            except Empty:
                # Timeout! Kill the worker and restart
                result = {
                    "status": "error",
                    "output": "",
                    "rich_output": None,
                    "error": f"TimeoutError: Cell execution timed out after {effective_timeout} seconds"
                }
                # Restart worker (this kills the hanging process)
                self._start_worker()
            
            # Ensure rich_output is present (worker doesn't return it)
            if "rich_output" not in result:
                result["rich_output"] = None
        finally:
            self._executing = False
            self._current_cell_id = None
        
        self.cell_outputs[cell_id] = result
        return result
    
    def get_variable(self, name: str) -> Any:
        """Get a variable from the namespace."""
        self._ensure_worker()
        
        try:
            self._request_queue.put({
                "type": CMD_GET_VAR,
                "name": name
            })
            response = self._response_queue.get(timeout=5)
            return response.get("value")
        except Exception:
            return None
    
    def set_variable(self, name: str, value: Any):
        """Set a variable in the namespace."""
        self._ensure_worker()
        
        try:
            self._request_queue.put({
                "type": CMD_SET_VAR,
                "name": name,
                "value": value
            })
            self._response_queue.get(timeout=5)
        except Exception:
            pass
    
    def __del__(self):
        """Clean up worker process on deletion."""
        self._stop_worker()
