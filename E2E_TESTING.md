# End-to-End Testing Guide

This document describes the E2E testing strategy for the Reactive Notebook.

## Current E2E Tests (Backend WebSocket)

The main E2E tests are located in `backend/test_e2e.py`. These tests simulate a full client-server interaction via WebSocket and cover:

### Test Coverage

1. **Regular Cell Processing** (`TestE2ERegularCellProcessing`)
   - Simple cell execution
   - Dependent cell execution (Excel-style reactive updates)
   - Error handling in cells

2. **Duplicate Variables** (`TestE2EDuplicateVariables`)
   - Detection of duplicate variable definitions across cells
   - Fixing duplicates to resume normal operation

3. **Circular Dependencies** (`TestE2ECircularDependencies`)
   - Two-way circular dependency detection (A → B → A)
   - Three-way circular dependencies (A → B → C → A)

4. **Timeout Handling** (`TestE2ETimeoutHandling`)
   - Infinite loop timeout
   - Kernel recovery after timeout
   - Note: Skipped on Windows (multiprocessing limitation)

5. **Complex Scenarios** (`TestE2EComplexScenario`)
   - Multi-cell dependency chains
   - Reactive propagation across multiple cells
   - Excel-style execution order

6. **Cell Management** (`TestE2EAddAndDeleteCells`)
   - Adding cells
   - Deleting cells

### Running E2E Tests

```bash
# Run all E2E tests
cd backend
python -m pytest test_e2e.py -v

# Run specific test class
python -m pytest test_e2e.py::TestE2EDuplicateVariables -v

# Run with output shown
python -m pytest test_e2e.py -v -s

# Skip timeout tests (useful on Windows or slow systems)
python -m pytest test_e2e.py -v -k "not timeout"
```

### How the Tests Work

1. **Test Server**: Each test module starts a real FastAPI server in a background process
2. **WebSocket Client**: Tests use `websockets` library to connect and communicate
3. **Message Flow**: Tests send cell updates and verify the response message sequence
4. **Cleanup**: Tests backup and restore the default notebook to avoid interference

### Test Isolation

- Each test uses a shared server instance (faster)
- Cells use unique IDs per test to avoid conflicts
- The default notebook is backed up and restored between test runs

## Browser-Based E2E Testing (Optional)

For testing the actual UI, you can set up browser-based E2E tests using Playwright.

### Setup Playwright

```bash
# Install Playwright
cd frontend
npm install -D @playwright/test

# Install browsers
npx playwright install
```

### Create Playwright Configuration

Create `frontend/playwright.config.ts`:

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'cd ../backend && uvicorn main:app --host 127.0.0.1 --port 8000',
    url: 'http://localhost:8000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
```

### Example Playwright Test

Create `frontend/e2e/notebook.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.describe('Reactive Notebook E2E', () => {
  test('should execute cell and show output', async ({ page }) => {
    await page.goto('/');
    
    // Wait for Monaco editor to load
    await page.waitForSelector('.monaco-editor');
    
    // Click on the first cell
    const cell = page.locator('[data-testid="cell"]').first();
    await cell.click();
    
    // Type code into the editor
    await page.keyboard.type('x = 10\nx');
    
    // Press Shift+Enter to execute
    await page.keyboard.press('Shift+Enter');
    
    // Wait for execution and verify output
    await expect(page.locator('[data-testid="cell-output"]').first())
      .toContainText('10', { timeout: 5000 });
  });
  
  test('should detect circular dependency', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.monaco-editor');
    
    // First cell: a = b
    const firstCell = page.locator('[data-testid="cell"]').first();
    await firstCell.click();
    await page.keyboard.type('a = b');
    await page.keyboard.press('Shift+Enter');
    
    // Add new cell
    await page.keyboard.press('Control+Enter');
    
    // Second cell: b = a (creates cycle)
    await page.keyboard.type('b = a');
    await page.keyboard.press('Shift+Enter');
    
    // Should show circular dependency error
    await expect(page.locator('[data-testid="cell-error"]'))
      .toContainText('Circular dependency', { timeout: 5000 });
  });
  
  test('should handle timeout on infinite loop', async ({ page }) => {
    test.skip(process.platform === 'win32', 'Timeout not supported on Windows');
    
    await page.goto('/');
    await page.waitForSelector('.monaco-editor');
    
    const cell = page.locator('[data-testid="cell"]').first();
    await cell.click();
    
    // Create infinite loop
    await page.keyboard.type('while True: pass');
    await page.keyboard.press('Shift+Enter');
    
    // Should timeout and show error
    await expect(page.locator('[data-testid="cell-error"]'))
      .toContainText('TimeoutError', { timeout: 20000 });
  });
  
  test('should propagate changes reactively', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.monaco-editor');
    
    // Cell 1: result = x * 2
    const firstCell = page.locator('[data-testid="cell"]').first();
    await firstCell.click();
    await page.keyboard.type('result = x * 2\nresult');
    await page.keyboard.press('Shift+Enter');
    
    // Cell 2: x = 10
    await page.keyboard.press('Control+Enter');
    await page.keyboard.type('x = 10');
    await page.keyboard.press('Shift+Enter');
    
    // Both cells should execute, result should be 20
    await expect(firstCell.locator('[data-testid="cell-output"]'))
      .toContainText('20', { timeout: 5000 });
    
    // Change x to 5
    const secondCell = page.locator('[data-testid="cell"]').nth(1);
    await secondCell.click();
    
    // Select all and replace
    await page.keyboard.press('Control+A');
    await page.keyboard.type('x = 5');
    await page.keyboard.press('Shift+Enter');
    
    // Result should update to 10
    await expect(firstCell.locator('[data-testid="cell-output"]'))
      .toContainText('10', { timeout: 5000 });
  });
});
```

### Running Playwright Tests

```bash
# Run tests
cd frontend
npx playwright test

# Run with UI
npx playwright test --ui

# Run in headed mode (see browser)
npx playwright test --headed

# Generate code (record actions)
npx playwright codegen http://localhost:8000
```

### Adding Test IDs to Frontend

To make Playwright tests more reliable, add test IDs to your React components:

```typescript
// In your Cell component
<div data-testid="cell">
  <div data-testid="cell-output">{output}</div>
  {error && <div data-testid="cell-error">{error}</div>}
</div>
```

## Comparison: Backend vs Browser E2E Tests

| Aspect | Backend WebSocket Tests | Browser Playwright Tests |
|--------|------------------------|--------------------------|
| **Speed** | Fast (< 1 second per test) | Slower (3-5 seconds per test) |
| **Setup** | Simple (already done) | Requires Playwright install |
| **Coverage** | Backend logic + WebSocket | Full UI + user interactions |
| **Maintenance** | Easy | Medium (UI changes break tests) |
| **CI/CD** | Lightweight | Heavier (needs browser) |
| **Debugging** | Standard Python debugging | Visual traces + videos |
| **Use Case** | Business logic, API flow | User experience, UI bugs |

## Recommendations

1. **Use Backend E2E tests** (current implementation) for:
   - Testing core functionality (dependencies, execution, errors)
   - CI/CD pipelines
   - Quick feedback during development

2. **Use Browser E2E tests** (Playwright) for:
   - Testing user interactions (keyboard shortcuts, cell management)
   - Visual regression testing
   - Cross-browser compatibility
   - Pre-release smoke tests

3. **Best Practice**: Maintain both test types
   - Backend E2E: Run on every commit (fast, reliable)
   - Browser E2E: Run nightly or pre-release (comprehensive but slower)

