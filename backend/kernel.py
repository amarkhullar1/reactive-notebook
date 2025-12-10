"""Code execution engine for the reactive notebook."""
import ast
import sys
import signal
import platform
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr, contextmanager
from typing import Any, Optional


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
            
            output_parts = []
            if stdout_output:
                output_parts.append(stdout_output.rstrip())
            if result_value is not None:
                output_parts.append(repr(result_value))
            
            output = '\n'.join(output_parts)
            
            result = {
                "status": "success",
                "output": output,
                "error": stderr_output
            }
        
        except TimeoutError as e:
            result = {
                "status": "error",
                "output": stdout_capture.getvalue(),
                "error": f"TimeoutError: {str(e)}"
            }
        
        except Exception as e:
            result = {
                "status": "error",
                "output": stdout_capture.getvalue(),
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
