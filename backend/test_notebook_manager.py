"""Tests for the NotebookManager class."""
import json
import pytest
import tempfile
from pathlib import Path

from notebook_manager import NotebookManager


@pytest.fixture
def temp_notebooks_dir():
    """Create a temporary directory for notebooks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def manager(temp_notebooks_dir):
    """Create a NotebookManager with a temp directory."""
    return NotebookManager(temp_notebooks_dir)


class TestNotebookCRUD:
    """Tests for basic notebook CRUD operations."""
    
    def test_create_notebook(self, manager, temp_notebooks_dir):
        """Test creating a new notebook."""
        metadata = manager.create_notebook("Test Notebook")
        
        assert metadata.name == "Test Notebook"
        assert metadata.id.startswith("nb-")
        assert metadata.created_at is not None
        assert metadata.updated_at is not None
        
        # Check that file was created
        notebook_path = temp_notebooks_dir / f"{metadata.id}.json"
        assert notebook_path.exists()
        
        # Check that index was updated
        index_path = temp_notebooks_dir / "index.json"
        assert index_path.exists()
        with open(index_path) as f:
            index_data = json.load(f)
        assert len(index_data["notebooks"]) == 1
        assert index_data["notebooks"][0]["id"] == metadata.id
    
    def test_list_notebooks_empty(self, manager):
        """Test listing notebooks when none exist."""
        notebooks = manager.list_notebooks()
        assert notebooks == []
    
    def test_list_notebooks(self, manager):
        """Test listing notebooks."""
        manager.create_notebook("First")
        manager.create_notebook("Second")
        
        notebooks = manager.list_notebooks()
        assert len(notebooks) == 2
        # Should be sorted by updated_at descending (most recent first)
        assert notebooks[0].name == "Second"
        assert notebooks[1].name == "First"
    
    def test_delete_notebook(self, manager, temp_notebooks_dir):
        """Test deleting a notebook."""
        metadata = manager.create_notebook("To Delete")
        notebook_id = metadata.id
        notebook_path = temp_notebooks_dir / f"{notebook_id}.json"
        
        assert notebook_path.exists()
        assert manager.notebook_exists(notebook_id)
        
        result = manager.delete_notebook(notebook_id)
        
        assert result is True
        assert not notebook_path.exists()
        assert not manager.notebook_exists(notebook_id)
        assert len(manager.list_notebooks()) == 0
    
    def test_delete_nonexistent_notebook(self, manager):
        """Test deleting a notebook that doesn't exist."""
        result = manager.delete_notebook("nonexistent-id")
        assert result is False
    
    def test_rename_notebook(self, manager):
        """Test renaming a notebook."""
        metadata = manager.create_notebook("Original Name")
        notebook_id = metadata.id
        
        result = manager.rename_notebook(notebook_id, "New Name")
        
        assert result is True
        updated_metadata = manager.get_metadata(notebook_id)
        assert updated_metadata.name == "New Name"
    
    def test_rename_nonexistent_notebook(self, manager):
        """Test renaming a notebook that doesn't exist."""
        result = manager.rename_notebook("nonexistent-id", "New Name")
        assert result is False


class TestNotebookLoading:
    """Tests for loading notebooks and lazy initialization."""
    
    def test_get_notebook_creates_engine(self, manager):
        """Test that getting a notebook creates a ReactiveEngine."""
        metadata = manager.create_notebook("Test")
        engine = manager.get_notebook(metadata.id)
        
        assert engine is not None
        assert len(engine.get_cells_in_order()) == 0
    
    def test_get_notebook_lazy_loading(self, manager):
        """Test that engines are not created until accessed."""
        metadata = manager.create_notebook("Test")
        
        # Engine should not be created yet
        assert metadata.id not in manager._engines
        
        # Access the notebook
        engine = manager.get_notebook(metadata.id)
        
        # Now engine should exist
        assert metadata.id in manager._engines
        assert engine is manager._engines[metadata.id]
    
    def test_get_nonexistent_notebook(self, manager):
        """Test getting a notebook that doesn't exist."""
        engine = manager.get_notebook("nonexistent-id")
        assert engine is None
    
    def test_notebook_persists_cells(self, manager, temp_notebooks_dir):
        """Test that cells are persisted when saved."""
        metadata = manager.create_notebook("Test")
        engine = manager.get_notebook(metadata.id)
        
        # Add a cell
        cell = engine.add_cell(code="x = 42")
        manager.save_notebook(metadata.id)
        
        # Check the file
        notebook_path = temp_notebooks_dir / f"{metadata.id}.json"
        with open(notebook_path) as f:
            data = json.load(f)
        
        assert len(data["cells"]) == 1
        assert data["cells"][0]["code"] == "x = 42"
    
    def test_notebook_loads_cells(self, temp_notebooks_dir):
        """Test that cells are loaded when notebook is opened."""
        # Create a notebook file manually
        notebook_id = "nb-test123"
        notebook_path = temp_notebooks_dir / f"{notebook_id}.json"
        with open(notebook_path, "w") as f:
            json.dump({
                "cells": [
                    {"id": "cell-1", "code": "x = 1", "output": "", "error": "", "status": "idle"},
                    {"id": "cell-2", "code": "y = x + 1", "output": "", "error": "", "status": "idle"}
                ]
            }, f)
        
        # Create index
        index_path = temp_notebooks_dir / "index.json"
        with open(index_path, "w") as f:
            json.dump({
                "notebooks": [{
                    "id": notebook_id,
                    "name": "Test Notebook",
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00"
                }]
            }, f)
        
        # Create a new manager (simulating server restart)
        manager = NotebookManager(temp_notebooks_dir)
        
        # Get the notebook
        engine = manager.get_notebook(notebook_id)
        
        assert engine is not None
        cells = engine.get_cells_in_order()
        assert len(cells) == 2
        assert cells[0].code == "x = 1"
        assert cells[1].code == "y = x + 1"


class TestExecutionState:
    """Tests for execution state management."""
    
    def test_execution_state_default(self, manager):
        """Test default execution state for new notebooks."""
        metadata = manager.create_notebook("Test")
        
        assert manager.is_executing(metadata.id) is False
        assert manager.is_cancelled(metadata.id) is False
    
    def test_set_execution_state(self, manager):
        """Test setting execution state."""
        metadata = manager.create_notebook("Test")
        manager.get_notebook(metadata.id)  # Initialize engine
        
        manager.set_executing(metadata.id, True)
        assert manager.is_executing(metadata.id) is True
        
        manager.set_cancelled(metadata.id, True)
        assert manager.is_cancelled(metadata.id) is True
        
        manager.set_executing(metadata.id, False)
        manager.set_cancelled(metadata.id, False)
        assert manager.is_executing(metadata.id) is False
        assert manager.is_cancelled(metadata.id) is False


class TestMigration:
    """Tests for migrating old default.json to new format."""
    
    def test_migrate_default_notebook(self, temp_notebooks_dir):
        """Test migration of default.json."""
        # Create an old-style default.json
        default_path = temp_notebooks_dir / "default.json"
        with open(default_path, "w") as f:
            json.dump({
                "cells": [
                    {"id": "cell-old", "code": "x = 42", "output": "42", "error": "", "status": "success"}
                ]
            }, f)
        
        # Create manager (should trigger migration)
        manager = NotebookManager(temp_notebooks_dir)
        notebook_id = manager.migrate_default_notebook()
        
        assert notebook_id is not None
        
        # Check that new notebook exists
        assert manager.notebook_exists(notebook_id)
        metadata = manager.get_metadata(notebook_id)
        assert metadata.name == "Default Notebook"
        
        # Check that cells were migrated
        engine = manager.get_notebook(notebook_id)
        cells = engine.get_cells_in_order()
        assert len(cells) == 1
        assert cells[0].code == "x = 42"
        
        # Check that old file was renamed to backup
        assert not default_path.exists()
        assert (temp_notebooks_dir / "default.json.backup").exists()
    
    def test_no_migration_without_default(self, temp_notebooks_dir):
        """Test that migration doesn't happen without default.json."""
        manager = NotebookManager(temp_notebooks_dir)
        result = manager.migrate_default_notebook()
        
        assert result is None
    
    def test_no_migration_with_existing_notebooks(self, temp_notebooks_dir):
        """Test that migration doesn't happen if notebooks already exist."""
        # Create an index with existing notebooks
        index_path = temp_notebooks_dir / "index.json"
        with open(index_path, "w") as f:
            json.dump({
                "notebooks": [{
                    "id": "nb-existing",
                    "name": "Existing",
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00"
                }]
            }, f)
        
        # Create default.json (should not be migrated)
        default_path = temp_notebooks_dir / "default.json"
        with open(default_path, "w") as f:
            json.dump({"cells": []}, f)
        
        manager = NotebookManager(temp_notebooks_dir)
        result = manager.migrate_default_notebook()
        
        assert result is None
        assert default_path.exists()  # Should not have been renamed


class TestIsolatedNamespaces:
    """Tests for verifying notebooks have isolated namespaces."""
    
    def test_separate_namespaces(self, manager):
        """Test that different notebooks have separate namespaces."""
        # Create two notebooks
        nb1 = manager.create_notebook("Notebook 1")
        nb2 = manager.create_notebook("Notebook 2")
        
        engine1 = manager.get_notebook(nb1.id)
        engine2 = manager.get_notebook(nb2.id)
        
        # Add cells with same variable name
        cell1 = engine1.add_cell(code="x = 100")
        cell2 = engine2.add_cell(code="x = 200")
        
        # Execute both
        result1 = engine1.execute_cell(cell1.id)
        result2 = engine2.execute_cell(cell2.id)
        
        assert result1["status"] == "success"
        assert result2["status"] == "success"
        
        # Add cells to read the variable
        read_cell1 = engine1.add_cell(code="x")
        read_cell2 = engine2.add_cell(code="x")
        
        result1 = engine1.execute_cell(read_cell1.id)
        result2 = engine2.execute_cell(read_cell2.id)
        
        # Values should be different (isolated namespaces)
        assert "100" in result1["output"]
        assert "200" in result2["output"]

