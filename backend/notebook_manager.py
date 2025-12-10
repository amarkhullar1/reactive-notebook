"""Manager for multiple notebooks with isolated namespaces."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models import Cell, RichOutput, NotebookMetadata
from reactive import ReactiveEngine


class NotebookManager:
    """
    Manages multiple notebooks, each with its own ReactiveEngine and isolated namespace.
    
    Notebooks are persisted as individual JSON files with an index file tracking metadata.
    Kernels are loaded lazily when a notebook is accessed.
    """
    
    def __init__(self, notebooks_dir: Path):
        self.notebooks_dir = notebooks_dir
        self.notebooks_dir.mkdir(exist_ok=True)
        
        # In-memory state
        self._engines: dict[str, ReactiveEngine] = {}  # notebook_id -> engine
        self._metadata: dict[str, NotebookMetadata] = {}  # notebook_id -> metadata
        
        # Execution state per notebook
        self._execution_cancelled: dict[str, bool] = {}
        self._is_executing: dict[str, bool] = {}
        
        # Load index on startup
        self._load_index()
    
    @property
    def index_path(self) -> Path:
        return self.notebooks_dir / "index.json"
    
    def _notebook_path(self, notebook_id: str) -> Path:
        return self.notebooks_dir / f"{notebook_id}.json"
    
    def _load_index(self):
        """Load notebook index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r") as f:
                    data = json.load(f)
                    for nb_data in data.get("notebooks", []):
                        metadata = NotebookMetadata(**nb_data)
                        self._metadata[metadata.id] = metadata
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading notebook index: {e}")
    
    def _save_index(self):
        """Save notebook index to disk."""
        data = {
            "notebooks": [m.model_dump() for m in self._metadata.values()]
        }
        with open(self.index_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_notebook_cells(self, notebook_id: str) -> list[dict]:
        """Load cells from a notebook file."""
        path = self._notebook_path(notebook_id)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    return data.get("cells", [])
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading notebook {notebook_id}: {e}")
        return []
    
    def _save_notebook(self, notebook_id: str):
        """Save a single notebook to disk."""
        if notebook_id not in self._engines:
            return
        
        engine = self._engines[notebook_id]
        cells_data = [
            {
                "id": cell.id,
                "code": cell.code,
                "output": cell.output,
                "rich_output": cell.rich_output,
                "error": cell.error,
                "status": cell.status
            }
            for cell in engine.get_cells_in_order()
        ]
        
        path = self._notebook_path(notebook_id)
        with open(path, "w") as f:
            json.dump({"cells": cells_data}, f, indent=2)
        
        # Update metadata timestamp
        if notebook_id in self._metadata:
            self._metadata[notebook_id].updated_at = datetime.now(timezone.utc).isoformat()
            self._save_index()
    
    def list_notebooks(self) -> list[NotebookMetadata]:
        """List all available notebooks."""
        return sorted(
            self._metadata.values(),
            key=lambda m: m.updated_at,
            reverse=True  # Most recently updated first
        )
    
    def create_notebook(self, name: str) -> NotebookMetadata:
        """Create a new empty notebook."""
        notebook_id = f"nb-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        
        metadata = NotebookMetadata(
            id=notebook_id,
            name=name,
            created_at=now,
            updated_at=now
        )
        
        self._metadata[notebook_id] = metadata
        self._save_index()
        
        # Create empty notebook file
        path = self._notebook_path(notebook_id)
        with open(path, "w") as f:
            json.dump({"cells": []}, f, indent=2)
        
        return metadata
    
    def delete_notebook(self, notebook_id: str) -> bool:
        """Delete a notebook and its data."""
        if notebook_id not in self._metadata:
            return False
        
        # Stop the engine if running
        if notebook_id in self._engines:
            engine = self._engines[notebook_id]
            # Clean up kernel
            if hasattr(engine.kernel, '_stop_worker'):
                engine.kernel._stop_worker()
            del self._engines[notebook_id]
        
        # Clean up execution state
        self._execution_cancelled.pop(notebook_id, None)
        self._is_executing.pop(notebook_id, None)
        
        # Delete file
        path = self._notebook_path(notebook_id)
        if path.exists():
            path.unlink()
        
        # Remove from index
        del self._metadata[notebook_id]
        self._save_index()
        
        return True
    
    def rename_notebook(self, notebook_id: str, new_name: str) -> bool:
        """Rename a notebook."""
        if notebook_id not in self._metadata:
            return False
        
        self._metadata[notebook_id].name = new_name
        self._metadata[notebook_id].updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()
        return True
    
    def get_notebook(self, notebook_id: str) -> Optional[ReactiveEngine]:
        """
        Get the ReactiveEngine for a notebook, loading it if necessary.
        
        This implements lazy loading - the kernel is only started when
        the notebook is first accessed.
        """
        if notebook_id not in self._metadata:
            return None
        
        # Lazy load: create engine if not already loaded
        if notebook_id not in self._engines:
            engine = ReactiveEngine()
            
            # Load cells from disk
            cells_data = self._load_notebook_cells(notebook_id)
            for cell_data in cells_data:
                cell = Cell(**cell_data)
                engine.add_cell(cell.id, cell.code, position=None)
                # Restore output/error/status/rich_output
                if cell.id in engine.cells:
                    engine.cells[cell.id].output = cell.output
                    engine.cells[cell.id].rich_output = cell.rich_output.model_dump() if cell.rich_output else None
                    engine.cells[cell.id].error = cell.error
                    engine.cells[cell.id].status = cell.status
            
            self._engines[notebook_id] = engine
            self._execution_cancelled[notebook_id] = False
            self._is_executing[notebook_id] = False
        
        return self._engines[notebook_id]
    
    def get_metadata(self, notebook_id: str) -> Optional[NotebookMetadata]:
        """Get metadata for a notebook."""
        return self._metadata.get(notebook_id)
    
    def notebook_exists(self, notebook_id: str) -> bool:
        """Check if a notebook exists."""
        return notebook_id in self._metadata
    
    def save_notebook(self, notebook_id: str):
        """Save a notebook to disk (public method for use after cell changes)."""
        self._save_notebook(notebook_id)
    
    # Execution state management
    
    def is_executing(self, notebook_id: str) -> bool:
        """Check if a notebook has a running execution."""
        return self._is_executing.get(notebook_id, False)
    
    def set_executing(self, notebook_id: str, value: bool):
        """Set execution state for a notebook."""
        self._is_executing[notebook_id] = value
    
    def is_cancelled(self, notebook_id: str) -> bool:
        """Check if execution was cancelled for a notebook."""
        return self._execution_cancelled.get(notebook_id, False)
    
    def set_cancelled(self, notebook_id: str, value: bool):
        """Set cancellation state for a notebook."""
        self._execution_cancelled[notebook_id] = value
    
    def migrate_default_notebook(self):
        """
        Migrate the old default.json to the new multi-notebook format.
        
        Called once on startup if default.json exists but no index exists.
        """
        default_path = self.notebooks_dir / "default.json"
        
        # Only migrate if default.json exists and we have no notebooks yet
        if not default_path.exists() or self._metadata:
            return None
        
        try:
            # Read the old notebook
            with open(default_path, "r") as f:
                data = json.load(f)
            
            # Create a new notebook with the data
            notebook_id = f"nb-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()
            
            metadata = NotebookMetadata(
                id=notebook_id,
                name="Default Notebook",
                created_at=now,
                updated_at=now
            )
            
            self._metadata[notebook_id] = metadata
            self._save_index()
            
            # Copy cells to new notebook file
            path = self._notebook_path(notebook_id)
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            
            # Rename old file to backup
            backup_path = self.notebooks_dir / "default.json.backup"
            default_path.rename(backup_path)
            
            print(f"Migrated default.json to notebook '{notebook_id}'")
            return notebook_id
            
        except Exception as e:
            print(f"Error migrating default notebook: {e}")
            return None

