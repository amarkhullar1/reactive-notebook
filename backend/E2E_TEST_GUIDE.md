# E2E Test Quick Start

## Overview

The E2E tests in `test_e2e.py` test the complete flow of the reactive notebook including:

- ✅ Regular cell processing
- ✅ Duplicate variable detection
- ✅ Circular dependency detection  
- ✅ Timeout handling (infinite loops)
- ✅ Complex multi-cell scenarios
- ✅ Cell management (add/delete)

Total: **12 E2E tests** covering all major features.

## Running the Tests

```bash
# From the backend directory
cd backend
source ../venv/bin/activate

# Run all E2E tests
python -m pytest test_e2e.py -v

# Run with output shown (useful for debugging)
python -m pytest test_e2e.py -v -s

# Run a specific test class
python -m pytest test_e2e.py::TestE2EDuplicateVariables -v

# Run a specific test
python -m pytest test_e2e.py::TestE2ERegularCellProcessing::test_simple_cell_execution -v

# Skip timeout tests (useful on Windows or slow systems)
python -m pytest test_e2e.py -v -k "not timeout"
```

## What Gets Tested

### 1. Regular Cell Processing
- Simple cell execution with output
- Dependent cells executing in correct order
- Error handling and reporting

### 2. Duplicate Variables
- Detection when multiple cells define the same variable
- Error messages indicating which cells have duplicates
- Recovery after fixing duplicates

### 3. Circular Dependencies
- Detection of A → B → A cycles
- Detection of A → B → C → A cycles
- Clear error messages showing the cycle

### 4. Timeout Handling
- Infinite loops timeout after 15 seconds
- Kernel recovers and can execute new cells after timeout
- ⚠️ Skipped on Windows (multiprocessing limitation)

### 5. Complex Scenarios
- Multi-cell dependency chains (A → B → C)
- Excel-style reactive propagation
- Changing base values updates all dependents

### 6. Cell Management
- Adding new cells via WebSocket
- Deleting cells and cleanup

## Test Architecture

```
┌─────────────────────────────────────────┐
│         test_e2e.py                     │
│  (WebSocket client - pytest)            │
└────────────┬────────────────────────────┘
             │ WebSocket connection
             ↓
┌─────────────────────────────────────────┐
│    FastAPI Server (Background Process)  │
│         main.py                         │
└────────────┬────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────┐
│    ReactiveEngine + Kernel              │
│    reactive.py + kernel.py              │
└─────────────────────────────────────────┘
```

### Key Components

1. **Test Server Fixture** (`test_server`)
   - Starts FastAPI server in a background process
   - Uses port 8765 (different from dev/prod)
   - Backs up and restores the default notebook

2. **WebSocket Client Fixture** (`ws_client`)
   - Connects to the test server
   - Receives initial notebook state
   - Used by all test cases

3. **Test Isolation**
   - Each test uses unique cell IDs
   - Tests don't interfere with each other
   - Notebook state is cleaned up after test run

## Expected Output

```
test_e2e.py::TestE2ERegularCellProcessing::test_simple_cell_execution PASSED
test_e2e.py::TestE2ERegularCellProcessing::test_dependent_cell_execution PASSED
test_e2e.py::TestE2ERegularCellProcessing::test_cell_with_error PASSED
test_e2e.py::TestE2EDuplicateVariables::test_duplicate_variable_error PASSED
test_e2e.py::TestE2EDuplicateVariables::test_fixing_duplicate_allows_execution PASSED
test_e2e.py::TestE2ECircularDependencies::test_circular_dependency_detection PASSED
test_e2e.py::TestE2ECircularDependencies::test_three_way_circular_dependency PASSED
test_e2e.py::TestE2ETimeoutHandling::test_timeout_on_infinite_loop PASSED (or SKIPPED on Windows)
test_e2e.py::TestE2ETimeoutHandling::test_kernel_recovers_after_timeout PASSED (or SKIPPED on Windows)
test_e2e.py::TestE2EComplexScenario::test_complex_reactive_notebook_scenario PASSED
test_e2e.py::TestE2EAddAndDeleteCells::test_add_cell PASSED
test_e2e.py::TestE2EAddAndDeleteCells::test_delete_cell PASSED

======================== 12 passed in X.XXs ========================
```

## Troubleshooting

### "Connection refused" error
- Make sure no other server is running on port 8765
- Wait a bit longer for the server to start (increase sleep time in fixture)

### Tests hang or timeout
- Check if kernel timeouts are working (may not work on Windows)
- Increase timeout values in asyncio.wait_for() calls

### "Module not found" errors
- Make sure pytest-asyncio is installed: `pip install pytest-asyncio==0.21.1`
- Make sure websockets is installed: `pip install websockets==12.0`

### Port already in use
- Change TEST_PORT in test_e2e.py to a different port
- Kill any existing processes using port 8765

## Adding New E2E Tests

When adding new features, consider adding E2E tests:

1. Create a new test class in `test_e2e.py`
2. Use the `ws_client` fixture for WebSocket communication
3. Send messages matching the protocol in `models.py`
4. Verify the response message sequence
5. Use unique cell IDs to avoid conflicts

Example:

```python
class TestE2ENewFeature:
    @pytest.mark.asyncio
    async def test_new_feature(self, ws_client):
        # Send message
        await ws_client.send(json.dumps({
            "type": "cell_updated",
            "cell_id": "unique-test-id",
            "code": "x = 1"
        }))
        
        # Receive and verify responses
        msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
        data = json.loads(msg)
        assert data["type"] == "execution_queue"
```

## Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run E2E Tests
  run: |
    cd backend
    python -m pytest test_e2e.py -v --tb=short
```

Note: On Windows CI runners, timeout tests will be skipped automatically.

