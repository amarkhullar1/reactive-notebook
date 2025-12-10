"""Unit tests for the reactive engine and kernel."""
import pytest
from reactive import ReactiveEngine, CellData
from kernel import NotebookKernel


class TestNotebookKernel:
    """Tests for the code execution kernel."""
    
    def setup_method(self):
        self.kernel = NotebookKernel()
    
    def test_simple_assignment(self):
        result = self.kernel.execute_cell("cell1", "x = 10")
        assert result["status"] == "success"
        assert result["error"] == ""
        assert self.kernel.get_variable("x") == 10
    
    def test_expression_output(self):
        """Last expression value should be in output."""
        result = self.kernel.execute_cell("cell1", "x = 10\nx + 5")
        assert result["status"] == "success"
        assert "15" in result["output"]
    
    def test_print_output(self):
        result = self.kernel.execute_cell("cell1", "print('hello')")
        assert result["status"] == "success"
        assert "hello" in result["output"]
    
    def test_combined_print_and_expression(self):
        result = self.kernel.execute_cell("cell1", "print('hello')\n42")
        assert result["status"] == "success"
        assert "hello" in result["output"]
        assert "42" in result["output"]
    
    def test_syntax_error(self):
        result = self.kernel.execute_cell("cell1", "x = 10 +")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]
    
    def test_runtime_error(self):
        result = self.kernel.execute_cell("cell1", "1 / 0")
        assert result["status"] == "error"
        assert "ZeroDivisionError" in result["error"]
    
    def test_undefined_variable_error(self):
        result = self.kernel.execute_cell("cell1", "print(undefined_var)")
        assert result["status"] == "error"
        assert "NameError" in result["error"]
    
    def test_namespace_persistence(self):
        """Variables persist across cell executions."""
        self.kernel.execute_cell("cell1", "x = 10")
        result = self.kernel.execute_cell("cell2", "y = x + 5\ny")
        assert result["status"] == "success"
        assert "15" in result["output"]
    
    def test_empty_code(self):
        result = self.kernel.execute_cell("cell1", "")
        assert result["status"] == "success"
        assert result["output"] == ""
    
    def test_whitespace_only(self):
        result = self.kernel.execute_cell("cell1", "   \n\n   ")
        assert result["status"] == "success"
    
    def test_reset_clears_namespace(self):
        self.kernel.execute_cell("cell1", "x = 10")
        self.kernel.reset()
        result = self.kernel.execute_cell("cell2", "print(x)")
        assert result["status"] == "error"
        assert "NameError" in result["error"]
    
    def test_timeout_infinite_loop(self):
        """Infinite loops should timeout gracefully."""
        import platform
        if platform.system() == 'Windows':
            pytest.skip("Timeout not supported on Windows")
        
        # Create kernel with short timeout for testing
        kernel = NotebookKernel(timeout=1)
        result = kernel.execute_cell("cell1", "while True: pass")
        
        assert result["status"] == "error"
        assert "TimeoutError" in result["error"]
        assert "timed out" in result["error"].lower()
    
    def test_timeout_long_computation(self):
        """Long computations should timeout."""
        import platform
        if platform.system() == 'Windows':
            pytest.skip("Timeout not supported on Windows")
        
        kernel = NotebookKernel(timeout=1)
        # This will take way longer than 1 second
        result = kernel.execute_cell("cell1", """
import time
time.sleep(10)
""")
        
        assert result["status"] == "error"
        assert "TimeoutError" in result["error"]
    
    def test_timeout_custom_per_cell(self):
        """Can specify timeout per cell execution."""
        import platform
        if platform.system() == 'Windows':
            pytest.skip("Timeout not supported on Windows")
        
        kernel = NotebookKernel(timeout=60)  # Long default
        result = kernel.execute_cell("cell1", "while True: pass", timeout=1)
        
        assert result["status"] == "error"
        assert "TimeoutError" in result["error"]
    
    def test_fast_code_no_timeout(self):
        """Fast code should complete without timeout."""
        kernel = NotebookKernel(timeout=5)
        result = kernel.execute_cell("cell1", "x = sum(range(1000))\nx")
        
        assert result["status"] == "success"
        assert "499500" in result["output"]
    
    def test_namespace_reset_after_timeout(self):
        """Namespace is reset after timeout (worker process is killed and restarted)."""
        import platform
        if platform.system() == 'Windows':
            pytest.skip("Timeout not supported on Windows")
        
        kernel = NotebookKernel(timeout=1)
        
        # First set a variable
        kernel.execute_cell("cell1", "x = 42")
        assert kernel.get_variable("x") == 42
        
        # Then timeout - this kills and restarts the worker
        result = kernel.execute_cell("cell2", "while True: pass")
        assert result["status"] == "error"
        assert "TimeoutError" in result["error"]
        
        # Variable is gone because worker was restarted
        assert kernel.get_variable("x") is None
        
        # But the kernel still works for new code
        kernel.execute_cell("cell3", "y = 100")
        assert kernel.get_variable("y") == 100


class TestReactiveEngine:
    """Tests for the reactive engine (Excel-style DAG)."""
    
    def setup_method(self):
        self.engine = ReactiveEngine()
    
    def test_add_cell(self):
        cell = self.engine.add_cell(code="x = 10")
        assert cell.id in self.engine.cells
        assert cell.code == "x = 10"
        assert cell.status == "idle"
    
    def test_add_cell_with_position(self):
        self.engine.add_cell(cell_id="cell1")
        self.engine.add_cell(cell_id="cell2")
        self.engine.add_cell(cell_id="cell3", position=1)
        
        assert self.engine.cell_order == ["cell1", "cell3", "cell2"]
    
    def test_delete_cell(self):
        self.engine.add_cell(cell_id="cell1")
        assert self.engine.delete_cell("cell1") is True
        assert "cell1" not in self.engine.cells
    
    def test_delete_nonexistent_cell(self):
        assert self.engine.delete_cell("nonexistent") is False
    
    def test_get_cells_in_order(self):
        self.engine.add_cell(cell_id="cell1", code="x = 1")
        self.engine.add_cell(cell_id="cell2", code="y = 2")
        cells = self.engine.get_cells_in_order()
        assert len(cells) == 2
        assert cells[0].id == "cell1"
        assert cells[1].id == "cell2"
    
    def test_on_cell_changed_creates_cell(self):
        result = self.engine.on_cell_changed("new_cell", "x = 10")
        assert "new_cell" in self.engine.cells
        assert "execution_order" in result
    
    def test_on_cell_changed_updates_code(self):
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.on_cell_changed("cell1", "x = 20")
        assert self.engine.cells["cell1"].code == "x = 20"
    
    def test_execution_order_respects_dependencies(self):
        """
        Excel-style: when changing a cell that others depend on,
        those dependent cells are re-executed in topological order.
        
        Cell 1: a = 10
        Cell 2: b = a + 1 (depends on cell1)
        Cell 3: c = b + 1 (depends on cell2)
        
        When cell1 changes, cell2 and cell3 should also execute.
        """
        self.engine.add_cell(cell_id="cell1", code="a = 10")
        self.engine.add_cell(cell_id="cell2", code="b = a + 1")
        self.engine.add_cell(cell_id="cell3", code="c = b + 1")
        
        result = self.engine.on_cell_changed("cell1", "a = 20")
        order = result["execution_order"]
        
        # All cells should be in execution order
        assert "cell1" in order
        assert "cell2" in order
        assert "cell3" in order
        
        # Execution order must respect dependencies
        assert order.index("cell1") < order.index("cell2")
        assert order.index("cell2") < order.index("cell3")
    
    def test_execute_cell_success(self):
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        result = self.engine.execute_cell("cell1")
        
        assert result["status"] == "success"
        assert self.engine.cells["cell1"].status == "success"
    
    def test_execute_cell_error(self):
        self.engine.add_cell(cell_id="cell1", code="1/0")
        result = self.engine.execute_cell("cell1")
        
        assert result["status"] == "error"
        assert self.engine.cells["cell1"].status == "error"
        assert "ZeroDivisionError" in self.engine.cells["cell1"].error
    
    def test_downstream_cells_include_cells_above(self):
        """Excel-style: changing a cell affects dependent cells above it."""
        self.engine.add_cell(cell_id="cell1", code="result = x + 1")
        self.engine.add_cell(cell_id="cell2", code="x = 10")
        
        # Change cell2 (below), cell1 (above) should be in execution order
        result = self.engine.on_cell_changed("cell2", "x = 20")
        
        assert "cell1" in result["execution_order"]
        assert "cell2" in result["execution_order"]
    
    def test_cycle_detection(self):
        """Circular dependencies should be detected and reported."""
        self.engine.add_cell(cell_id="cell1", code="a = b")
        self.engine.add_cell(cell_id="cell2", code="b = a")
        
        result = self.engine.on_cell_changed("cell1", "a = b")
        
        assert "error" in result
        assert "Circular dependency detected" in result["error"]
        # Should use cell numbers, not cell IDs
        assert "cell 1" in result["error"]
        assert "cell 2" in result["error"]
    
    def test_execute_all_topological_order(self):
        """execute_all should run cells in topological order."""
        self.engine.add_cell(cell_id="cell1", code="result = x + y")
        self.engine.add_cell(cell_id="cell2", code="x = 10")
        self.engine.add_cell(cell_id="cell3", code="y = 20")
        
        results = self.engine.execute_all()
        
        # Find the result for cell1
        cell1_result = next(r for r in results if r["cell_id"] == "cell1")
        assert cell1_result["status"] == "success"
        
        # Verify result = 30
        assert self.engine.kernel.get_variable("result") == 30
    
    def test_reset_kernel(self):
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.execute_cell("cell1")
        
        self.engine.reset_kernel()
        
        assert self.engine.cells["cell1"].status == "idle"
        assert self.engine.cells["cell1"].output == ""


class TestDuplicateVariableDetection:
    """Tests for duplicate variable definition detection."""
    
    def setup_method(self):
        self.engine = ReactiveEngine()
    
    def test_duplicate_definition_error_on_cell_changed(self):
        """on_cell_changed should return error when duplicate definitions exist."""
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.add_cell(cell_id="cell2", code="y = 20")
        
        # Now change cell2 to also define x
        result = self.engine.on_cell_changed("cell2", "x = 30")
        
        assert "error" in result
        assert "Variable 'x' is defined in multiple cells" in result["error"]
        assert "cell 1" in result["error"]
        assert "cell 2" in result["error"]
    
    def test_duplicate_definition_error_on_execute_all(self):
        """execute_all should return error when duplicate definitions exist."""
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.add_cell(cell_id="cell2", code="x = 20")
        
        results = self.engine.execute_all()
        
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "Variable 'x' is defined in multiple cells: cell 1, cell 2" in results[0]["error"]
    
    def test_no_error_when_no_duplicates(self):
        """No error when each variable is defined in exactly one cell."""
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.add_cell(cell_id="cell2", code="y = x + 1")
        
        result = self.engine.on_cell_changed("cell1", "x = 20")
        
        assert "execution_order" in result
        assert "error" not in result
    
    def test_duplicate_sets_cell_error_status(self):
        """The changed cell should have error status when duplicates detected."""
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.add_cell(cell_id="cell2", code="y = 20")
        
        self.engine.on_cell_changed("cell2", "x = 30")
        
        assert self.engine.cells["cell2"].status == "error"
        assert "Variable 'x'" in self.engine.cells["cell2"].error
    
    def test_duplicate_checked_before_cycle(self):
        """Duplicate check should happen before cycle detection."""
        # Create a situation that would be both a cycle AND a duplicate
        self.engine.add_cell(cell_id="cell1", code="x = y")
        self.engine.add_cell(cell_id="cell2", code="y = x")  # This creates a cycle
        
        # Now also make it a duplicate by adding x definition to cell2
        result = self.engine.on_cell_changed("cell2", "x = 1\ny = x")
        
        # Should get duplicate error, not cycle error
        assert "error" in result
        assert "Variable 'x' is defined in multiple cells" in result["error"]
    
    def test_fixing_duplicate_allows_execution(self):
        """After fixing a duplicate, execution should work."""
        self.engine.add_cell(cell_id="cell1", code="x = 10")
        self.engine.add_cell(cell_id="cell2", code="x = 20")  # Duplicate!
        
        # Verify duplicate is detected
        result = self.engine.on_cell_changed("cell2", "x = 20")
        assert "error" in result
        
        # Fix by changing cell2 to not define x
        result = self.engine.on_cell_changed("cell2", "y = x + 1")
        
        assert "execution_order" in result
        assert "error" not in result
    
    def test_multiple_duplicates_all_reported(self):
        """When multiple variables are duplicated, all are reported."""
        self.engine.add_cell(cell_id="cell1", code="x = 10\ny = 20")
        self.engine.add_cell(cell_id="cell2", code="z = 30")
        
        # Change cell2 to define both x and y
        result = self.engine.on_cell_changed("cell2", "x = 1\ny = 2")
        
        assert "error" in result
        assert "x" in result["error"]
        assert "y" in result["error"]


class TestReactiveExecution:
    """Integration tests for reactive execution flow."""
    
    def setup_method(self):
        self.engine = ReactiveEngine()
    
    def test_full_reactive_flow(self):
        """
        Complete flow: add cells, execute, change, re-execute.
        
        Cell 1: result = x * 2
        Cell 2: x = 5
        
        Change x to 10 -> result should become 20
        """
        # Add cells
        self.engine.add_cell(cell_id="cell1", code="result = x * 2")
        self.engine.add_cell(cell_id="cell2", code="x = 5")
        
        # Execute all
        self.engine.execute_all()
        assert self.engine.kernel.get_variable("result") == 10
        
        # Change cell2
        order = self.engine.on_cell_changed("cell2", "x = 10")
        
        # Execute in order
        for cell_id in order["execution_order"]:
            self.engine.execute_cell(cell_id)
        
        assert self.engine.kernel.get_variable("result") == 20
    
    def test_chain_propagation(self):
        """
        Changes propagate through the entire chain.
        
        Cell 1: a = 1
        Cell 2: b = a + 1
        Cell 3: c = b + 1
        Cell 4: d = c + 1
        
        Change a to 10 -> d should become 13
        """
        self.engine.add_cell(cell_id="cell1", code="a = 1")
        self.engine.add_cell(cell_id="cell2", code="b = a + 1")
        self.engine.add_cell(cell_id="cell3", code="c = b + 1")
        self.engine.add_cell(cell_id="cell4", code="d = c + 1")
        
        self.engine.execute_all()
        assert self.engine.kernel.get_variable("d") == 4
        
        # Change cell1
        order = self.engine.on_cell_changed("cell1", "a = 10")
        for cell_id in order["execution_order"]:
            self.engine.execute_cell(cell_id)
        
        assert self.engine.kernel.get_variable("d") == 13
    
    def test_diamond_dependency(self):
        """
        Diamond pattern: A -> B, A -> C, B -> D, C -> D
        
        Cell 1: a = 1
        Cell 2: b = a * 2
        Cell 3: c = a * 3
        Cell 4: d = b + c
        """
        self.engine.add_cell(cell_id="cell1", code="a = 1")
        self.engine.add_cell(cell_id="cell2", code="b = a * 2")
        self.engine.add_cell(cell_id="cell3", code="c = a * 3")
        self.engine.add_cell(cell_id="cell4", code="d = b + c")
        
        self.engine.execute_all()
        assert self.engine.kernel.get_variable("d") == 5  # 2 + 3
        
        # Change a to 10
        order = self.engine.on_cell_changed("cell1", "a = 10")
        for cell_id in order["execution_order"]:
            self.engine.execute_cell(cell_id)
        
        assert self.engine.kernel.get_variable("d") == 50  # 20 + 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

