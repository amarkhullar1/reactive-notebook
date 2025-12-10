# E2E Tests - Quick Start Guide

## ✅ E2E Tests Are Ready!

I've created comprehensive end-to-end tests for your reactive notebook in `backend/test_e2e.py`.

## What's Tested

- ✅ **Regular cell processing** - Simple execution, dependent cells, errors
- ✅ **Duplicate variables** - Detection and recovery  
- ✅ **Circular dependencies** - 2-way and 3-way cycles
- ✅ **Timeout handling** - Infinite loops and recovery (skipped on Windows)
- ✅ **Complex scenarios** - Multi-cell reactive propagation
- ✅ **Cell management** - Adding and deleting cells

**Total: 12 E2E tests**

## Running the Tests

```bash
# Install dependencies (one-time setup)
cd backend
source ../venv/bin/activate
pip install -r ../requirements.txt

# Run individual test (recommended)
python -m pytest test_e2e.py::TestE2ERegularCellProcessing::test_simple_cell_execution -v

# Run a test class
python -m pytest test_e2e.py::TestE2EDuplicateVariables -v

# Skip timeout tests (Windows or slow systems)
python -m pytest test_e2e.py -v -k "not timeout"

# List all tests
python -m pytest test_e2e.py --collect-only
```

## Backend vs Browser E2E Tests

### Current Implementation: Backend WebSocket Tests ✅

**Why backend E2E tests?**
- ✅ Fast (< 1 second per test)
- ✅ Tests core business logic
- ✅ Tests WebSocket protocol
- ✅ Easy to set up (uses existing pytest)
- ✅ CI/CD friendly (no browser required)

**What it tests:**
- WebSocket message flow
- Dependency detection (duplicates, cycles)
- Execution order
- Timeout handling
- Error propagation

**What it doesn't test:**
- UI rendering
- User interactions (clicks, keyboard)
- Monaco editor integration
- Visual appearance

### Optional: Browser-Based Tests with Playwright

If you need to test the actual UI, see `E2E_TESTING.md` for a complete guide on setting up Playwright browser tests.

## Test Architecture

```
┌────────────────────────────────────┐
│   test_e2e.py                      │
│   (pytest + websockets client)     │
└──────────────┬─────────────────────┘
               │ WebSocket
               ↓
┌────────────────────────────────────┐
│   FastAPI Server                   │
│   (background process)             │
└──────────────┬─────────────────────┘
               │
               ↓
┌────────────────────────────────────┐
│   ReactiveEngine + Kernel          │
└────────────────────────────────────┘
```

## Example Test

Here's what a test looks like:

```python
async def test_duplicate_variable_error(self, ws_client):
    """Test that duplicate variable definitions are detected."""
    # Create cell 1: x = 10
    await ws_client.send(json.dumps({
        "type": "cell_updated",
        "cell_id": "dup-cell-1",
        "code": "x = 10"
    }))
    
    # Consume response messages
    for _ in range(3):  # queue, started, result
        await asyncio.wait_for(ws_client.recv(), timeout=5)
    
    # Create cell 2: x = 20 (duplicate!)
    await ws_client.send(json.dumps({
        "type": "cell_updated",
        "cell_id": "dup-cell-2",
        "code": "x = 20"
    }))
    
    # Should receive error message
    msg = await asyncio.wait_for(ws_client.recv(), timeout=5)
    error_data = json.loads(msg)
    
    assert error_data["type"] == "error"
    assert "Variable 'x' is defined in multiple cells" in error_data["message"]
```

## Files Created

1. **`backend/test_e2e.py`** - Main E2E test suite (12 tests)
2. **`backend/pytest.ini`** - Pytest configuration for async tests
3. **`E2E_TESTING.md`** - Comprehensive guide (backend + browser testing)
4. **`E2E_TEST_SUMMARY.md`** - Detailed implementation overview
5. **`backend/E2E_TEST_GUIDE.md`** - Detailed test running guide
6. **Updated `requirements.txt`** - Added pytest-asyncio
7. **Updated `README.md`** - Added E2E test documentation

## Dependencies Added

- `pytest==8.4.2` - Testing framework (compatible version)
- `pytest-asyncio==1.3.0` - Async test support
- `websockets==12.0` - WebSocket client (already had it)

## Common Issues

### Port already in use
Change `TEST_PORT` in `test_e2e.py` to a different port.

### Connection refused
Wait a bit longer for the server to start (increase sleep time in fixture).

### Tests hang
Some tests may take longer due to server startup. Individual tests run faster than running all tests together.

## Next Steps

1. ✅ Run the tests to verify they work in your environment
2. ✅ Add E2E tests to your CI/CD pipeline
3. Optional: Set up Playwright for browser testing (see E2E_TESTING.md)
4. ✅ Expand coverage as you add new features

## Documentation

- **Quick guide**: `E2E_QUICK_START.md` (this file)
- **Comprehensive guide**: `E2E_TESTING.md` 
- **Implementation details**: `E2E_TEST_SUMMARY.md`
- **Running tests**: `backend/E2E_TEST_GUIDE.md`

## Summary

✅ **Done!** You now have comprehensive E2E tests that cover:
- Regular cell processing
- Duplicate variable detection
- Circular dependency detection
- Timeout handling
- Complex reactive scenarios

The tests use WebSocket communication to test the full stack (Frontend protocol → Backend → Engine → Kernel) without requiring a browser.

