"""Dependency analysis using Python AST to detect variable definitions and usages."""
import ast
import builtins
from typing import Optional


# Set of Python built-in names to ignore
BUILTINS = set(dir(builtins))


class DependencyAnalyzer:
    """Analyzes Python code to identify variable definitions and usages."""
    
    @staticmethod
    def get_defined_vars(code: str) -> set[str]:
        """
        Parse code and find all variable names that are defined/assigned.
        
        Handles:
        - Simple assignments: x = 1
        - Multiple assignments: x, y = 1, 2
        - Augmented assignments: x += 1
        - Annotated assignments: x: int = 1
        - Function definitions: def foo(): ...
        - Class definitions: class Foo: ...
        - For loop variables: for x in ...
        - With statement variables: with ... as x:
        - Import statements: import x, from y import x
        - Comprehension variables (scoped, so we skip these)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()
        
        defined = set()
        
        for node in ast.walk(tree):
            # Simple assignment: x = 1, x, y = 1, 2
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    defined.update(DependencyAnalyzer._extract_names(target))
            
            # Augmented assignment: x += 1
            elif isinstance(node, ast.AugAssign):
                defined.update(DependencyAnalyzer._extract_names(node.target))
            
            # Annotated assignment: x: int = 1
            elif isinstance(node, ast.AnnAssign):
                if node.target:
                    defined.update(DependencyAnalyzer._extract_names(node.target))
            
            # Function definition: def foo():
            elif isinstance(node, ast.FunctionDef):
                defined.add(node.name)
            
            # Async function definition: async def foo():
            elif isinstance(node, ast.AsyncFunctionDef):
                defined.add(node.name)
            
            # Class definition: class Foo:
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
            
            # For loop: for x in ...
            elif isinstance(node, ast.For):
                defined.update(DependencyAnalyzer._extract_names(node.target))
            
            # With statement: with ... as x:
            elif isinstance(node, ast.With):
                for item in node.items:
                    if item.optional_vars:
                        defined.update(DependencyAnalyzer._extract_names(item.optional_vars))
            
            # Import: import x, import x as y
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name.split('.')[0]
                    defined.add(name)
            
            # From import: from x import y, from x import y as z
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    if name != '*':
                        defined.add(name)
        
        # Filter out internal variables (starting with _)
        return {v for v in defined if not v.startswith('_')}
    
    @staticmethod
    def _extract_names(node: ast.AST) -> set[str]:
        """Extract variable names from an assignment target."""
        names = set()
        
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
            for elt in node.elts:
                names.update(DependencyAnalyzer._extract_names(elt))
        elif isinstance(node, ast.Starred):
            names.update(DependencyAnalyzer._extract_names(node.value))
        
        return names
    
    @staticmethod
    def get_used_vars(code: str) -> set[str]:
        """
        Parse code and find all variable names that are used/referenced.
        
        Only includes names that are loaded (read), not stored (written).
        Filters out built-ins and names starting with _.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()
        
        used = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
                # Skip built-ins and internal names
                if name not in BUILTINS and not name.startswith('_'):
                    used.add(name)
        
        return used
    
    @staticmethod
    def get_dependencies(code: str) -> tuple[set[str], set[str]]:
        """
        Get both defined and used variables for a piece of code.
        
        Returns:
            Tuple of (defined_vars, used_vars)
        """
        return (
            DependencyAnalyzer.get_defined_vars(code),
            DependencyAnalyzer.get_used_vars(code)
        )
    
    @staticmethod
    def build_dependency_graph(cells: list[tuple[str, str]]) -> dict[str, set[str]]:
        """
        Build a dependency graph from a list of cells.
        
        Args:
            cells: List of (cell_id, code) tuples in order
        
        Returns:
            Dict mapping cell_id to set of cell_ids it depends on
            (i.e., cells that define variables this cell uses)
        """
        # First pass: collect what each cell defines
        cell_defines: dict[str, set[str]] = {}
        cell_uses: dict[str, set[str]] = {}
        
        for cell_id, code in cells:
            defined, used = DependencyAnalyzer.get_dependencies(code)
            cell_defines[cell_id] = defined
            cell_uses[cell_id] = used
        
        # Build mapping of variable -> cell that defines it (last definition wins)
        # We process in order so later cells override earlier ones
        var_to_cell: dict[str, str] = {}
        cell_order = [cell_id for cell_id, _ in cells]
        
        for cell_id, code in cells:
            for var in cell_defines[cell_id]:
                var_to_cell[var] = cell_id
        
        # Second pass: for each cell, find which cells it depends on
        # A cell depends on another if it uses a variable that the other defines
        # AND the defining cell comes before the using cell
        dependencies: dict[str, set[str]] = {cell_id: set() for cell_id, _ in cells}
        
        for cell_id, code in cells:
            cell_idx = cell_order.index(cell_id)
            
            for var in cell_uses[cell_id]:
                # Find which cell defines this variable
                # We need to find the most recent definition BEFORE this cell
                defining_cell = None
                for i in range(cell_idx - 1, -1, -1):
                    other_id = cell_order[i]
                    if var in cell_defines[other_id]:
                        defining_cell = other_id
                        break
                
                if defining_cell and defining_cell != cell_id:
                    dependencies[cell_id].add(defining_cell)
        
        return dependencies
    
    @staticmethod
    def find_downstream_cells(
        cell_id: str,
        cells: list[tuple[str, str]]
    ) -> set[str]:
        """
        Find all cells that depend on the given cell (directly or transitively).
        
        Args:
            cell_id: The cell that was changed
            cells: List of (cell_id, code) tuples in order
        
        Returns:
            Set of cell IDs that need to be re-executed
        """
        # Build dependency graph
        dep_graph = DependencyAnalyzer.build_dependency_graph(cells)
        
        # Build reverse graph (cell -> cells that depend on it)
        reverse_graph: dict[str, set[str]] = {cid: set() for cid, _ in cells}
        for cid, deps in dep_graph.items():
            for dep in deps:
                reverse_graph[dep].add(cid)
        
        # BFS to find all downstream cells
        downstream = set()
        queue = list(reverse_graph.get(cell_id, set()))
        
        while queue:
            current = queue.pop(0)
            if current not in downstream:
                downstream.add(current)
                queue.extend(reverse_graph.get(current, set()))
        
        return downstream
    
    @staticmethod
    def topological_sort(
        cell_ids: set[str],
        cells: list[tuple[str, str]]
    ) -> list[str]:
        """
        Topologically sort the given cells based on dependencies.
        
        Uses Kahn's algorithm. Only sorts the given subset but uses
        the full dependency graph for ordering.
        
        Args:
            cell_ids: Set of cell IDs to sort
            cells: List of all (cell_id, code) tuples in order
        
        Returns:
            List of cell IDs in valid execution order
        """
        if not cell_ids:
            return []
        
        # Build dependency graph for the subset
        full_dep_graph = DependencyAnalyzer.build_dependency_graph(cells)
        
        # Filter to only include edges within our subset
        dep_graph = {
            cid: deps & cell_ids
            for cid, deps in full_dep_graph.items()
            if cid in cell_ids
        }
        
        # Calculate in-degrees
        in_degree = {cid: 0 for cid in cell_ids}
        for cid, deps in dep_graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[cid] = in_degree.get(cid, 0) + 1
        
        # Start with nodes that have no dependencies
        queue = [cid for cid in cell_ids if in_degree[cid] == 0]
        
        # Sort queue by original cell order for deterministic output
        cell_order = [cell_id for cell_id, _ in cells]
        queue.sort(key=lambda x: cell_order.index(x) if x in cell_order else float('inf'))
        
        result = []
        while queue:
            # Take the first cell (maintains original order when possible)
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree for cells that depend on current
            for cid in cell_ids:
                if current in dep_graph.get(cid, set()):
                    in_degree[cid] -= 1
                    if in_degree[cid] == 0:
                        queue.append(cid)
                        queue.sort(key=lambda x: cell_order.index(x) if x in cell_order else float('inf'))
        
        return result
    
    @staticmethod
    def has_cycle(cells: list[tuple[str, str]]) -> Optional[str]:
        """
        Detect if there's a circular dependency in the cells.
        
        Returns:
            Error message if cycle detected, None otherwise
        """
        dep_graph = DependencyAnalyzer.build_dependency_graph(cells)
        
        # DFS with three states: unvisited, in-progress, completed
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {cid: WHITE for cid, _ in cells}
        
        def dfs(node: str, path: list[str]) -> Optional[str]:
            color[node] = GRAY
            path.append(node)
            
            for dep in dep_graph.get(node, set()):
                if color[dep] == GRAY:
                    # Found cycle
                    cycle_start = path.index(dep)
                    cycle = path[cycle_start:] + [dep]
                    return f"Circular dependency detected: {' -> '.join(cycle)}"
                elif color[dep] == WHITE:
                    result = dfs(dep, path)
                    if result:
                        return result
            
            path.pop()
            color[node] = BLACK
            return None
        
        for cell_id, _ in cells:
            if color[cell_id] == WHITE:
                result = dfs(cell_id, [])
                if result:
                    return result
        
        return None

