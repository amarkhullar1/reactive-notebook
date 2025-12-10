"""Reactive execution engine for the notebook."""
import uuid
from dataclasses import dataclass, field
from typing import Optional

from kernel import NotebookKernel
from dependency import DependencyAnalyzer


@dataclass
class CellData:
    """Internal cell representation."""
    id: str
    code: str = ""
    output: str = ""
    error: str = ""
    status: str = "idle"  # idle, running, success, error


class ReactiveEngine:
    """
    Manages notebook cells and handles reactive re-execution (Excel-style DAG).
    
    Unlike Jupyter-style notebooks, cells can depend on ANY other cell
    regardless of their vertical position. Dependencies are based purely
    on which symbols a cell reads and which cell defines those symbols.
    
    When a cell is changed:
    1. Rebuild the dependency graph (order-independent)
    2. Check for circular dependencies
    3. Find all transitively dependent cells (can be above or below)
    4. Topologically sort them based on the dependency DAG
    5. Execute in dependency order (not display order)
    """
    
    def __init__(self):
        self.cells: dict[str, CellData] = {}
        self.cell_order: list[str] = []  # Maintains display order (UI only)
        self.kernel = NotebookKernel()
        self.analyzer = DependencyAnalyzer()
    
    def add_cell(
        self,
        cell_id: Optional[str] = None,
        code: str = "",
        position: Optional[int] = None
    ) -> CellData:
        """
        Add a new cell to the notebook.
        
        Args:
            cell_id: Optional ID for the cell (generated if not provided)
            code: Initial code for the cell
            position: Position to insert at (appends if None)
        
        Returns:
            The created CellData
        """
        if cell_id is None:
            cell_id = f"cell-{uuid.uuid4().hex[:8]}"
        
        cell = CellData(id=cell_id, code=code)
        self.cells[cell_id] = cell
        
        if position is not None and 0 <= position <= len(self.cell_order):
            self.cell_order.insert(position, cell_id)
        else:
            self.cell_order.append(cell_id)
        
        return cell
    
    def delete_cell(self, cell_id: str) -> bool:
        """
        Delete a cell from the notebook.
        
        Args:
            cell_id: ID of the cell to delete
        
        Returns:
            True if cell was deleted, False if not found
        """
        if cell_id not in self.cells:
            return False
        
        del self.cells[cell_id]
        self.cell_order.remove(cell_id)
        return True
    
    def get_cells_in_order(self) -> list[CellData]:
        """Get all cells in display order."""
        return [self.cells[cell_id] for cell_id in self.cell_order if cell_id in self.cells]
    
    def _get_cells_as_tuples(self) -> list[tuple[str, str]]:
        """Get cells as (id, code) tuples in order."""
        return [(cell_id, self.cells[cell_id].code) for cell_id in self.cell_order if cell_id in self.cells]
    
    def _format_duplicate_error(self, duplicates: dict[str, list[str]]) -> str:
        """Format a user-friendly error message for duplicate variable definitions."""
        lines = []
        for var, cell_ids in duplicates.items():
            # Convert cell IDs to 1-indexed cell numbers based on display order
            cell_numbers = []
            for cell_id in cell_ids:
                if cell_id in self.cell_order:
                    cell_num = self.cell_order.index(cell_id) + 1  # 1-indexed
                    cell_numbers.append(f"cell {cell_num}")
                else:
                    cell_numbers.append(cell_id)  # Fallback to ID if not found
            cells_str = ", ".join(cell_numbers)
            lines.append(f"Variable '{var}' is defined in multiple cells: {cells_str}")
        return "Each variable must be defined in exactly one cell.\n" + "\n".join(lines)
    
    def _format_cycle_error(self, cycle: list[str]) -> str:
        """Format a user-friendly error message for circular dependencies."""
        # Convert cell IDs to 1-indexed cell numbers based on display order
        cell_numbers = []
        for cell_id in cycle:
            if cell_id in self.cell_order:
                cell_num = self.cell_order.index(cell_id) + 1  # 1-indexed
                cell_numbers.append(f"cell {cell_num}")
            else:
                cell_numbers.append(cell_id)  # Fallback to ID if not found
        return f"Circular dependency detected: {' → '.join(cell_numbers)}"
    
    def on_cell_changed(self, cell_id: str, new_code: str) -> dict:
        """
        Handle a cell code change and determine what needs to be re-executed.
        
        Args:
            cell_id: ID of the changed cell
            new_code: New code content
        
        Returns:
            Dict with either:
            - {"error": "error message"} if there's a problem
            - {"execution_order": [list of cell_ids]} for cells to execute
        """
        # Update the cell code
        if cell_id not in self.cells:
            # Cell doesn't exist, create it
            self.add_cell(cell_id=cell_id, code=new_code)
        else:
            self.cells[cell_id].code = new_code
        
        # Get cells as tuples for analysis
        cells_tuples = self._get_cells_as_tuples()
        
        # Check for duplicate variable definitions
        duplicates = self.analyzer.find_duplicate_definitions(cells_tuples)
        if duplicates:
            error_msg = self._format_duplicate_error(duplicates)
            self.cells[cell_id].status = "error"
            self.cells[cell_id].error = error_msg
            return {"error": error_msg}
        
        # Check for circular dependencies
        cycle = self.analyzer.find_cycle(cells_tuples)
        if cycle:
            error_msg = self._format_cycle_error(cycle)
            self.cells[cell_id].status = "error"
            self.cells[cell_id].error = error_msg
            return {"error": error_msg}
        
        # Find downstream cells that need re-execution
        downstream = self.analyzer.find_downstream_cells(cell_id, cells_tuples)
        
        # Include the changed cell itself
        dirty_cells = {cell_id} | downstream
        
        # Topologically sort to get execution order
        execution_order = self.analyzer.topological_sort(dirty_cells, cells_tuples)
        
        return {"execution_order": execution_order}
    
    def execute_cell(self, cell_id: str) -> dict:
        """
        Execute a single cell.
        
        Args:
            cell_id: ID of the cell to execute
        
        Returns:
            Execution result dict with status, output, error
        """
        if cell_id not in self.cells:
            return {
                "status": "error",
                "output": "",
                "error": f"Cell {cell_id} not found"
            }
        
        cell = self.cells[cell_id]
        cell.status = "running"
        
        # Execute the code
        result = self.kernel.execute_cell(cell_id, cell.code)
        
        # Update cell state
        cell.status = result["status"]
        cell.output = result["output"]
        cell.error = result["error"]
        
        return result
    
    def execute_all(self) -> list[dict]:
        """
        Execute all cells in topological order (respecting dependencies).
        
        Returns:
            List of execution results in execution order
        """
        cells_tuples = self._get_cells_as_tuples()
        
        # Check for duplicate variable definitions first
        duplicates = self.analyzer.find_duplicate_definitions(cells_tuples)
        if duplicates:
            error_msg = self._format_duplicate_error(duplicates)
            return [{"cell_id": None, "status": "error", "output": "", "error": error_msg}]
        
        # Check for cycles
        cycle = self.analyzer.find_cycle(cells_tuples)
        if cycle:
            error_msg = self._format_cycle_error(cycle)
            return [{"cell_id": None, "status": "error", "output": "", "error": error_msg}]
        
        # Get all cell IDs and sort topologically
        all_cell_ids = set(self.cell_order)
        execution_order = self.analyzer.topological_sort(all_cell_ids, cells_tuples)
        
        results = []
        for cell_id in execution_order:
            result = self.execute_cell(cell_id)
            results.append({"cell_id": cell_id, **result})
        return results
    
    def reset_kernel(self):
        """Reset the kernel namespace."""
        self.kernel.reset()
        for cell in self.cells.values():
            cell.status = "idle"
            cell.output = ""
            cell.error = ""

