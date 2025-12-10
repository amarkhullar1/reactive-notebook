"""Code execution engine for the reactive notebook."""
import ast
import sys
import signal
import platform
import math
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr, contextmanager
from typing import Any, Optional

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
DEFAULT_TIMEOUT = 15


class TimeoutError(Exception):
    """Raised when code execution times out."""
    pass


@contextmanager
def timeout_handler(seconds: int):
    """
    Context manager that raises TimeoutError after specified seconds.
    
    Uses signal.SIGALRM on Unix systems. On Windows, timeout is not enforced
    (Windows doesn't support SIGALRM).
    """
    if platform.system() == 'Windows':
        # Windows doesn't support SIGALRM, so we can't enforce timeout
        # The code will run without timeout protection
        yield
        return
    
    def signal_handler(signum, frame):
        raise TimeoutError(f"Cell execution timed out after {seconds} seconds")
    
    # Set the signal handler
    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    
    # Schedule the alarm
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # Cancel the alarm
        signal.alarm(0)
        # Restore the old handler
        signal.signal(signal.SIGALRM, old_handler)


class NotebookKernel:
    """
    Executes Python code in a shared namespace.
    
    Features:
    - Persistent namespace across cell executions
    - Captures stdout and stderr
    - Returns the value of the last expression (like Jupyter)
    - Timeout handling for long-running or infinite loops
    """
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.namespace: dict[str, Any] = {}
        self.cell_outputs: dict[str, dict] = {}
        self.timeout = timeout
    
    def reset(self):
        """Reset the kernel namespace."""
        self.namespace.clear()
        self.cell_outputs.clear()
    
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
        if not code.strip():
            return {
                "status": "success",
                "output": "",
                "rich_output": None,
                "error": ""
            }
        
        effective_timeout = timeout if timeout is not None else self.timeout
        
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        result_value = None
        
        try:
            # Parse the code first (outside timeout since parsing is fast)
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                return {
                    "status": "error",
                    "output": "",
                    "rich_output": None,
                    "error": f"SyntaxError: {e.msg} (line {e.lineno})"
                }
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                with timeout_handler(effective_timeout):
                    if tree.body and isinstance(tree.body[-1], ast.Expr):
                        # Last statement is an expression - eval it to capture value
                        # Execute all but the last statement
                        if len(tree.body) > 1:
                            module = ast.Module(body=tree.body[:-1], type_ignores=[])
                            exec(compile(module, '<cell>', 'exec'), self.namespace)
                        
                        # Eval the last expression
                        last_expr = ast.Expression(body=tree.body[-1].value)
                        result_value = eval(compile(last_expr, '<cell>', 'eval'), self.namespace)
                    else:
                        # No trailing expression, just exec everything
                        exec(compile(tree, '<cell>', 'exec'), self.namespace)
            
            # Build output: stdout + repr of last expression (if any)
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()
            
            # Try to create rich output for DataFrames, arrays, etc.
            rich_output = serialize_rich_output(result_value)
            
            output_parts = []
            if stdout_output:
                output_parts.append(stdout_output.rstrip())
            if result_value is not None:
                output_parts.append(repr(result_value))
            
            output = '\n'.join(output_parts)
            
            result = {
                "status": "success",
                "output": output,
                "rich_output": rich_output,
                "error": stderr_output
            }
        
        except TimeoutError as e:
            result = {
                "status": "error",
                "output": stdout_capture.getvalue(),
                "rich_output": None,
                "error": f"TimeoutError: {str(e)}"
            }
        
        except Exception as e:
            result = {
                "status": "error",
                "output": stdout_capture.getvalue(),
                "rich_output": None,
                "error": f"{type(e).__name__}: {str(e)}"
            }
        
        self.cell_outputs[cell_id] = result
        return result
    
    def get_variable(self, name: str) -> Any:
        """Get a variable from the namespace."""
        return self.namespace.get(name)
    
    def set_variable(self, name: str, value: Any):
        """Set a variable in the namespace."""
        self.namespace[name] = value
