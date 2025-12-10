"""
End-to-end tests for the reactive notebook.

These tests simulate a full client-server interaction via WebSocket,
testing the complete flow from cell updates to execution results.
"""
import pytest
import asyncio
import json
import websockets
from websockets.exceptions import ConnectionClosed
import platform
import multiprocessing
import uvicorn
import time
from pathlib import Path
import shutil


# Test server configuration
TEST_HOST = "127.0.0.1"
TEST_PORT = 8765
TEST_WS_URL = f"ws://{TEST_HOST}:{TEST_PORT}/ws"

# Backup path for default notebook during tests
TEST_NOTEBOOKS_DIR = Path(__file__).parent.parent / "notebooks"
BACKUP_NOTEBOOK = TEST_NOTEBOOKS_DIR / "default.json.backup"


def run_test_server():
    """Run the FastAPI server in a separate process."""
    import sys
    from pathlib import Path
    
    # Add backend to path
    backend_dir = Path(__file__).parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    
    from main import app
    
    # Run server
    uvicorn.run(app, host=TEST_HOST, port=TEST_PORT, log_level="error")


@pytest.fixture(scope="module", autouse=True)
def test_server():
    """Start test server in background process."""
    # Backup existing notebook if it exists
    default_notebook = TEST_NOTEBOOKS_DIR / "default.json"
    if default_notebook.exists():
        shutil.copy(default_notebook, BACKUP_NOTEBOOK)
        default_notebook.unlink()
    
    # Start server process (daemon=False to allow child processes)
    ctx = multiprocessing.get_context('spawn')
    server_process = ctx.Process(target=run_test_server)
    server_process.start()
    
    # Wait for server to be ready
    time.sleep(3)
    
    yield
    
    # Cleanup
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()
    
    # Restore backup
    if BACKUP_NOTEBOOK.exists():
        shutil.move(BACKUP_NOTEBOOK, default_notebook)


@pytest.fixture
async def ws_client():
    """Create a WebSocket client connection."""
    async with websockets.connect(TEST_WS_URL) as websocket:
        # Receive initial notebook state
        initial_msg = await websocket.recv()
        initial_data = json.loads(initial_msg)
        assert initial_data["type"] == "notebook_state"
        
        yield websocket


class TestE2ERegularCellProcessing:
    """E2E tests for regular cell processing."""
    
    @pytest.mark.asyncio
    async def test_simple_cell_execution(self, ws_client):
        """Test basic cell creation and execution."""
        # Update a cell with simple code
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "test-cell-1",
            "code": "x = 10\nx"
        }))
        
        # Should receive: execution_queue, execution_started, execution_result
        messages = []
        for _ in range(3):
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        # Verify execution queue
        assert messages[0]["type"] == "execution_queue"
        assert "test-cell-1" in messages[0]["cell_ids"]
        
        # Verify execution started
        assert messages[1]["type"] == "execution_started"
        assert messages[1]["cell_id"] == "test-cell-1"
        
        # Verify execution result
        assert messages[2]["type"] == "execution_result"
        assert messages[2]["cell_id"] == "test-cell-1"
        assert messages[2]["status"] == "success"
        assert "10" in messages[2]["output"]
    
    @pytest.mark.asyncio
    async def test_dependent_cell_execution(self, ws_client):
        """Test that dependent cells are automatically re-executed."""
        # Create cell 1: y = x + 5
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "test-cell-1",
            "code": "y = x + 5"
        }))
        
        # Consume messages
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        # Create cell 2: x = 10 (cell 1 depends on this)
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "test-cell-2",
            "code": "x = 10"
        }))
        
        # Should execute both cells in correct order
        messages = []
        for _ in range(6):  # Queue + 2 * (started + result)
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        # Verify execution queue contains both cells
        queue_msg = messages[0]
        assert queue_msg["type"] == "execution_queue"
        assert "test-cell-2" in queue_msg["cell_ids"]
        assert "test-cell-1" in queue_msg["cell_ids"]
        
        # Verify cell-2 executes before cell-1 (dependency order)
        cell_2_idx = queue_msg["cell_ids"].index("test-cell-2")
        cell_1_idx = queue_msg["cell_ids"].index("test-cell-1")
        assert cell_2_idx < cell_1_idx
        
        # Verify both executed successfully
        result_messages = [m for m in messages if m["type"] == "execution_result"]
        assert len(result_messages) == 2
        assert all(m["status"] == "success" for m in result_messages)
    
    @pytest.mark.asyncio
    async def test_cell_with_error(self, ws_client):
        """Test that cell errors are properly reported."""
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "test-error-cell",
            "code": "1 / 0"
        }))
        
        messages = []
        for _ in range(3):
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        result_msg = messages[2]
        assert result_msg["type"] == "execution_result"
        assert result_msg["status"] == "error"
        assert "ZeroDivisionError" in result_msg["error"]


class TestE2EDuplicateVariables:
    """E2E tests for duplicate variable detection."""
    
    @pytest.mark.asyncio
    async def test_duplicate_variable_error(self, ws_client):
        """Test that duplicate variable definitions are detected."""
        # Create cell 1: x = 10
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "dup-cell-1",
            "code": "x = 10"
        }))
        
        # Consume messages
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        # Create cell 2: x = 20 (duplicate!)
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "dup-cell-2",
            "code": "x = 20"
        }))
        
        # Should receive an error message
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        error_data = json.loads(msg)
        
        assert error_data["type"] == "error"
        assert "Variable 'x' is defined in multiple cells" in error_data["message"]
    
    @pytest.mark.asyncio
    async def test_fixing_duplicate_allows_execution(self, ws_client):
        """Test that fixing a duplicate allows normal execution."""
        # Create duplicate
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "fix-cell-1",
            "code": "z = 10"
        }))
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "fix-cell-2",
            "code": "z = 20"
        }))
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        error_data = json.loads(msg)
        assert error_data["type"] == "error"
        
        # Fix by changing variable name
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "fix-cell-2",
            "code": "w = z + 1"
        }))
        
        # Should now execute successfully
        messages = []
        for _ in range(6):  # Queue + 2 * (started + result)
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        result_messages = [m for m in messages if m["type"] == "execution_result"]
        assert all(m["status"] == "success" for m in result_messages)


class TestE2ECircularDependencies:
    """E2E tests for circular dependency detection."""
    
    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self, ws_client):
        """Test that circular dependencies are detected and reported."""
        # Create cell 1: a = b
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "circ-cell-1",
            "code": "a = b"
        }))
        
        # Consume messages
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        # Create cell 2: b = a (creates cycle!)
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "circ-cell-2",
            "code": "b = a"
        }))
        
        # Should receive error message
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        error_data = json.loads(msg)
        
        assert error_data["type"] == "error"
        assert "Circular dependency detected" in error_data["message"]
    
    @pytest.mark.asyncio
    async def test_three_way_circular_dependency(self, ws_client):
        """Test detection of A -> B -> C -> A cycle."""
        # Create cells with circular dependency
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "cycle-a",
            "code": "a = c + 1"
        }))
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "cycle-b",
            "code": "b = a + 1"
        }))
        for _ in range(6):
            await asyncio.wait_for(ws_client.recv(), timeout=5)
        
        # This creates the cycle
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "cycle-c",
            "code": "c = b + 1"
        }))
        
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        error_data = json.loads(msg)
        
        assert error_data["type"] == "error"
        assert "Circular dependency detected" in error_data["message"]


class TestE2ETimeoutHandling:
    """E2E tests for timeout handling."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        platform.system() == 'Windows',
        reason="Timeout not supported on Windows"
    )
    async def test_timeout_on_infinite_loop(self, ws_client):
        """Test that infinite loops timeout gracefully."""
        # Send cell with infinite loop
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "timeout-cell",
            "code": "while True: pass"
        }))
        
        # Should receive queue, started, then result with timeout error
        messages = []
        
        # Wait up to 20 seconds for timeout (default is 15s)
        for _ in range(3):
            msg = await asyncio.wait_for(ws_client.recv(), timeout=20)
            messages.append(json.loads(msg))
        
        result_msg = messages[2]
        assert result_msg["type"] == "execution_result"
        assert result_msg["status"] == "error"
        assert "TimeoutError" in result_msg["error"]
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        platform.system() == 'Windows',
        reason="Timeout not supported on Windows"
    )
    async def test_kernel_recovers_after_timeout(self, ws_client):
        """Test that kernel can execute cells after a timeout."""
        # First, cause a timeout
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "timeout-cell-1",
            "code": "import time\ntime.sleep(20)"
        }))
        
        # Wait for timeout
        for _ in range(3):
            await asyncio.wait_for(ws_client.recv(), timeout=20)
        
        # Now execute a normal cell
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "recovery-cell",
            "code": "recovered = True\nrecovered"
        }))
        
        messages = []
        for _ in range(3):
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        result_msg = messages[2]
        assert result_msg["type"] == "execution_result"
        assert result_msg["status"] == "success"
        assert "True" in result_msg["output"]


class TestE2EComplexScenario:
    """E2E test combining multiple features."""
    
    @pytest.mark.asyncio
    async def test_complex_reactive_notebook_scenario(self, ws_client):
        """
        Complex scenario testing:
        - Multiple cells with dependencies
        - Excel-style reactive execution
        - Error handling
        - Variable propagation
        """
        # Cell 1: Define base value
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "scenario-base",
            "code": "base = 10"
        }))
        for _ in range(3):
            await ws_client.recv()
        
        # Cell 2: Use base value (depends on cell 1)
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "scenario-derived",
            "code": "derived = base * 2"
        }))
        for _ in range(6):  # Both cells execute
            await ws_client.recv()
        
        # Cell 3: Use derived value (depends on cell 2)
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "scenario-final",
            "code": "final = derived + 5\nfinal"
        }))
        for _ in range(9):  # All three cells execute
            await ws_client.recv()
        
        # Now change the base value - all dependent cells should re-execute
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "scenario-base",
            "code": "base = 100"
        }))
        
        # Collect all messages
        messages = []
        for _ in range(9):  # Queue + 3 * (started + result)
            msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
            messages.append(json.loads(msg))
        
        # Verify execution queue
        queue_msg = messages[0]
        assert queue_msg["type"] == "execution_queue"
        assert len(queue_msg["cell_ids"]) == 3
        
        # Verify all cells executed in dependency order
        assert queue_msg["cell_ids"].index("scenario-base") < \
               queue_msg["cell_ids"].index("scenario-derived")
        assert queue_msg["cell_ids"].index("scenario-derived") < \
               queue_msg["cell_ids"].index("scenario-final")
        
        # Verify final result is correct (100 * 2 + 5 = 205)
        result_messages = [m for m in messages if m["type"] == "execution_result"]
        final_result = [m for m in result_messages if m["cell_id"] == "scenario-final"][0]
        assert final_result["status"] == "success"
        assert "205" in final_result["output"]


class TestE2EAddAndDeleteCells:
    """E2E tests for adding and deleting cells."""
    
    @pytest.mark.asyncio
    async def test_add_cell(self, ws_client):
        """Test adding a new cell."""
        await ws_client.send(json.dumps({
            "type": "add_cell",
            "position": 0
        }))
        
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        data = json.loads(msg)
        
        assert data["type"] == "cell_added"
        assert "cell" in data
        assert data["cell"]["code"] == ""
        assert data["cell"]["status"] == "idle"
    
    @pytest.mark.asyncio
    async def test_delete_cell(self, ws_client):
        """Test deleting a cell."""
        # First add a cell
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "delete-test",
            "code": "x = 1"
        }))
        for _ in range(3):
            await ws_client.recv()
        
        # Delete it
        await ws_client.send(json.dumps({
            "type": "delete_cell",
            "cell_id": "delete-test"
        }))
        
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        data = json.loads(msg)
        
        assert data["type"] == "cell_deleted"
        assert data["cell_id"] == "delete-test"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

