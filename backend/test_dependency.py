"""Unit tests for the dependency analyzer (Excel-style DAG)."""
import pytest
from dependency import DependencyAnalyzer


class TestGetDefinedVars:
    """Tests for get_defined_vars function."""
    
    def test_simple_assignment(self):
        code = "x = 10"
        assert DependencyAnalyzer.get_defined_vars(code) == {"x"}
    
    def test_multiple_assignments(self):
        code = "x = 10\ny = 20\nz = 30"
        assert DependencyAnalyzer.get_defined_vars(code) == {"x", "y", "z"}
    
    def test_tuple_unpacking(self):
        code = "x, y = 1, 2"
        assert DependencyAnalyzer.get_defined_vars(code) == {"x", "y"}
    
    def test_augmented_assignment(self):
        code = "x += 10"
        assert DependencyAnalyzer.get_defined_vars(code) == {"x"}
    
    def test_annotated_assignment(self):
        code = "x: int = 10"
        assert DependencyAnalyzer.get_defined_vars(code) == {"x"}
    
    def test_function_definition(self):
        code = "def foo():\n    pass"
        assert DependencyAnalyzer.get_defined_vars(code) == {"foo"}
    
    def test_class_definition(self):
        code = "class MyClass:\n    pass"
        assert DependencyAnalyzer.get_defined_vars(code) == {"MyClass"}
    
    def test_for_loop_variable(self):
        code = "for i in range(10):\n    pass"
        assert DependencyAnalyzer.get_defined_vars(code) == {"i"}
    
    def test_import_statement(self):
        code = "import pandas"
        assert DependencyAnalyzer.get_defined_vars(code) == {"pandas"}
    
    def test_import_as(self):
        code = "import pandas as pd"
        assert DependencyAnalyzer.get_defined_vars(code) == {"pd"}
    
    def test_from_import(self):
        code = "from math import sqrt"
        assert DependencyAnalyzer.get_defined_vars(code) == {"sqrt"}
    
    def test_syntax_error_returns_empty(self):
        code = "x = 10 +"
        assert DependencyAnalyzer.get_defined_vars(code) == set()
    
    def test_empty_code(self):
        code = ""
        assert DependencyAnalyzer.get_defined_vars(code) == set()
    
    def test_private_vars_filtered(self):
        code = "_private = 10\n__dunder__ = 20\npublic = 30"
        assert DependencyAnalyzer.get_defined_vars(code) == {"public"}


class TestGetUsedVars:
    """Tests for get_used_vars function."""
    
    def test_simple_usage(self):
        code = "y = x + 1"
        assert DependencyAnalyzer.get_used_vars(code) == {"x"}
    
    def test_multiple_usages(self):
        code = "z = x + y"
        assert DependencyAnalyzer.get_used_vars(code) == {"x", "y"}
    
    def test_function_call(self):
        code = "result = foo(x)"
        assert DependencyAnalyzer.get_used_vars(code) == {"foo", "x"}
    
    def test_builtin_filtered(self):
        code = "y = len(x)"
        # len is a builtin, should be filtered
        assert DependencyAnalyzer.get_used_vars(code) == {"x"}
    
    def test_print_filtered(self):
        code = "print(x)"
        assert DependencyAnalyzer.get_used_vars(code) == {"x"}
    
    def test_syntax_error_returns_empty(self):
        code = "y = x +"
        assert DependencyAnalyzer.get_used_vars(code) == set()
    
    def test_empty_code(self):
        code = ""
        assert DependencyAnalyzer.get_used_vars(code) == set()
    
    def test_self_assignment(self):
        # In "x = x + 1", x is both used and defined
        code = "x = x + 1"
        assert DependencyAnalyzer.get_used_vars(code) == {"x"}
        assert DependencyAnalyzer.get_defined_vars(code) == {"x"}


class TestBuildDependencyGraph:
    """Tests for build_dependency_graph (Excel-style DAG)."""
    
    def test_simple_chain(self):
        """Cell 2 depends on Cell 1."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell1"] == set()
        assert deps["cell2"] == {"cell1"}
    
    def test_reverse_order_dependency(self):
        """Cell 1 depends on Cell 2 (Excel-style: order doesn't matter)."""
        cells = [
            ("cell1", "y = x + 1"),  # Uses x
            ("cell2", "x = 10"),     # Defines x
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        # In Excel-style, cell1 should depend on cell2
        assert deps["cell1"] == {"cell2"}
        assert deps["cell2"] == set()
    
    def test_diamond_dependency(self):
        r"""
        Cell 4 depends on Cells 2 and 3, which both depend on Cell 1.
        
            Cell1 (a=1)
            /        \
        Cell2 (b=a) Cell3 (c=a)
            \        /
            Cell4 (d=b+c)
        """
        cells = [
            ("cell1", "a = 1"),
            ("cell2", "b = a"),
            ("cell3", "c = a"),
            ("cell4", "d = b + c"),
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell1"] == set()
        assert deps["cell2"] == {"cell1"}
        assert deps["cell3"] == {"cell1"}
        assert deps["cell4"] == {"cell2", "cell3"}
    
    def test_no_dependencies(self):
        """Independent cells have no dependencies."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = 20"),
            ("cell3", "z = 30"),
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell1"] == set()
        assert deps["cell2"] == set()
        assert deps["cell3"] == set()
    
    def test_self_reference_no_dependency(self):
        """A cell doesn't depend on itself."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "x = x + 1"),  # Uses x defined in cell1
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell2"] == {"cell1"}
    
    def test_first_definer_wins(self):
        """When multiple cells define the same var, first one wins."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "x = 20"),  # Also defines x
            ("cell3", "y = x"),   # Should depend on cell1 (first definer)
        ]
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell3"] == {"cell1"}


class TestFindDownstreamCells:
    """Tests for find_downstream_cells (order-independent)."""
    
    def test_direct_dependents(self):
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
        ]
        downstream = DependencyAnalyzer.find_downstream_cells("cell1", cells)
        assert downstream == {"cell2"}
    
    def test_transitive_dependents(self):
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
            ("cell3", "z = y + 1"),
        ]
        downstream = DependencyAnalyzer.find_downstream_cells("cell1", cells)
        assert downstream == {"cell2", "cell3"}
    
    def test_upstream_cell_changed(self):
        """When a downstream cell is changed, upstream cells are NOT affected."""
        cells = [
            ("cell1", "y = x + 1"),  # Depends on cell2
            ("cell2", "x = 10"),
        ]
        downstream = DependencyAnalyzer.find_downstream_cells("cell1", cells)
        # cell2 does NOT depend on cell1
        assert downstream == set()
    
    def test_downstream_includes_cells_above(self):
        """Excel-style: downstream cells can be above the changed cell."""
        cells = [
            ("cell1", "result = x + y"),  # Depends on cell2 and cell3
            ("cell2", "x = 10"),
            ("cell3", "y = 20"),
        ]
        # Changing cell3 should trigger cell1 (which is above it)
        downstream = DependencyAnalyzer.find_downstream_cells("cell3", cells)
        assert "cell1" in downstream
    
    def test_no_dependents(self):
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = 20"),
        ]
        downstream = DependencyAnalyzer.find_downstream_cells("cell1", cells)
        assert downstream == set()


class TestTopologicalSort:
    """Tests for topological_sort."""
    
    def test_simple_chain(self):
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
            ("cell3", "z = y + 1"),
        ]
        order = DependencyAnalyzer.topological_sort({"cell1", "cell2", "cell3"}, cells)
        # cell1 must come before cell2, cell2 before cell3
        assert order.index("cell1") < order.index("cell2")
        assert order.index("cell2") < order.index("cell3")
    
    def test_reverse_display_order(self):
        """Execution order can differ from display order."""
        cells = [
            ("cell1", "result = x + y"),  # Depends on cell2, cell3
            ("cell2", "x = 10"),
            ("cell3", "y = 20"),
        ]
        order = DependencyAnalyzer.topological_sort({"cell1", "cell2", "cell3"}, cells)
        # cell2 and cell3 must come before cell1
        assert order.index("cell2") < order.index("cell1")
        assert order.index("cell3") < order.index("cell1")
    
    def test_partial_subset(self):
        """Only sort the given subset of cells."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
            ("cell3", "z = y + 1"),
        ]
        # Only sort cell2 and cell3
        order = DependencyAnalyzer.topological_sort({"cell2", "cell3"}, cells)
        assert order.index("cell2") < order.index("cell3")
        assert "cell1" not in order
    
    def test_independent_cells_use_display_order(self):
        """Independent cells are sorted by display order (tiebreaker)."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = 20"),
            ("cell3", "z = 30"),
        ]
        order = DependencyAnalyzer.topological_sort({"cell1", "cell2", "cell3"}, cells)
        assert order == ["cell1", "cell2", "cell3"]
    
    def test_empty_set(self):
        cells = [("cell1", "x = 10")]
        order = DependencyAnalyzer.topological_sort(set(), cells)
        assert order == []


class TestHasCycle:
    """Tests for cycle detection."""
    
    def test_no_cycle(self):
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "y = x + 1"),
        ]
        assert DependencyAnalyzer.has_cycle(cells) is None
    
    def test_direct_cycle(self):
        """A -> B -> A creates a cycle."""
        cells = [
            ("cell1", "x = y"),  # Uses y from cell2
            ("cell2", "y = x"),  # Uses x from cell1
        ]
        result = DependencyAnalyzer.has_cycle(cells)
        assert result is not None
        assert "Circular dependency" in result
    
    def test_indirect_cycle(self):
        """A -> B -> C -> A creates a cycle."""
        cells = [
            ("cell1", "a = c"),
            ("cell2", "b = a"),
            ("cell3", "c = b"),
        ]
        result = DependencyAnalyzer.has_cycle(cells)
        assert result is not None
        assert "Circular dependency" in result
    
    def test_self_reference_no_cycle(self):
        """A cell using a variable it defines is NOT a cycle."""
        cells = [
            ("cell1", "x = 10"),
            ("cell2", "x = x + 1"),  # Uses x from cell1, defines x
        ]
        assert DependencyAnalyzer.has_cycle(cells) is None


class TestExcelStyleBehavior:
    """Integration tests for Excel-style DAG behavior."""
    
    def test_cell_above_depends_on_cell_below(self):
        """
        The key Excel-style behavior: a cell can depend on cells below it.
        
        Display order:
            Cell 1: result = x + y  (depends on x, y)
            Cell 2: x = 10
            Cell 3: y = 20
        
        Execution order should be: Cell 2 -> Cell 3 -> Cell 1
        """
        cells = [
            ("cell1", "result = x + y"),
            ("cell2", "x = 10"),
            ("cell3", "y = 20"),
        ]
        
        # Build dependency graph
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell1"] == {"cell2", "cell3"}  # Depends on both
        assert deps["cell2"] == set()
        assert deps["cell3"] == set()
        
        # Topological sort
        order = DependencyAnalyzer.topological_sort({"cell1", "cell2", "cell3"}, cells)
        assert order.index("cell2") < order.index("cell1")
        assert order.index("cell3") < order.index("cell1")
        
        # No cycle
        assert DependencyAnalyzer.has_cycle(cells) is None
    
    def test_change_bottom_cell_affects_top(self):
        """Changing a cell at the bottom should affect cells at the top."""
        cells = [
            ("cell1", "result = x + y"),
            ("cell2", "x = 10"),
            ("cell3", "y = 20"),
        ]
        
        # If we change cell3, cell1 should be in downstream
        downstream = DependencyAnalyzer.find_downstream_cells("cell3", cells)
        assert "cell1" in downstream
        
        # cell2 should NOT be affected
        assert "cell2" not in downstream
    
    def test_mixed_dependency_directions(self):
        """
        Complex case with dependencies going both up and down.
        
        Cell 1: a = 1
        Cell 2: b = a + c  (depends on cell1 above, cell3 below)
        Cell 3: c = 10
        Cell 4: d = b * 2  (depends on cell2)
        """
        cells = [
            ("cell1", "a = 1"),
            ("cell2", "b = a + c"),
            ("cell3", "c = 10"),
            ("cell4", "d = b * 2"),
        ]
        
        deps = DependencyAnalyzer.build_dependency_graph(cells)
        assert deps["cell2"] == {"cell1", "cell3"}  # Depends on both above and below
        assert deps["cell4"] == {"cell2"}
        
        # Execution order should respect dependencies
        order = DependencyAnalyzer.topological_sort(
            {"cell1", "cell2", "cell3", "cell4"}, cells
        )
        assert order.index("cell1") < order.index("cell2")
        assert order.index("cell3") < order.index("cell2")
        assert order.index("cell2") < order.index("cell4")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

