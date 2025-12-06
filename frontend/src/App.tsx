import { useState, useEffect, useRef, useCallback } from 'react';
import { Cell } from './Cell';
import { createWebSocketClient, type WebSocketClient } from './websocket';
import type { Cell as CellType, ServerMessage } from './types';

function App() {
  const [cells, setCells] = useState<CellType[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocketClient | null>(null);
  const debounceTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Handle incoming WebSocket messages
  const handleMessage = useCallback((message: ServerMessage) => {
    switch (message.type) {
      case 'notebook_state':
        setCells(message.cells);
        break;

      case 'cell_added':
        setCells((prev) => {
          const newCells = [...prev];
          newCells.splice(message.position, 0, message.cell);
          return newCells;
        });
        break;

      case 'cell_deleted':
        setCells((prev) => prev.filter((c) => c.id !== message.cell_id));
        break;

      case 'execution_started':
        setCells((prev) =>
          prev.map((c) =>
            c.id === message.cell_id ? { ...c, status: 'running' as const } : c
          )
        );
        break;

      case 'execution_result':
        setCells((prev) =>
          prev.map((c) =>
            c.id === message.cell_id
              ? {
                  ...c,
                  status: message.status,
                  output: message.output,
                  error: message.error,
                }
              : c
          )
        );
        break;

      case 'execution_queue':
        // Mark all queued cells as pending execution
        setCells((prev) =>
          prev.map((c) =>
            message.cell_ids.includes(c.id) && c.status !== 'running'
              ? { ...c, status: 'running' as const }
              : c
          )
        );
        break;

      case 'error':
        // Handle error messages (e.g., circular dependency)
        if (message.cell_id) {
          setCells((prev) =>
            prev.map((c) =>
              c.id === message.cell_id
                ? { ...c, status: 'error' as const, error: message.message }
                : c
            )
          );
        } else {
          console.error('Server error:', message.message);
        }
        break;
    }
  }, []);

  // Initialize WebSocket connection
  useEffect(() => {
    // Determine WebSocket URL based on environment
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // In development, Vite proxy handles /ws
    // In production, connect directly
    const wsUrl = import.meta.env.DEV 
      ? `${protocol}//${host}/ws`
      : `${protocol}//${host}/ws`;

    wsRef.current = createWebSocketClient(wsUrl, handleMessage, setConnected);

    return () => {
      wsRef.current?.close();
    };
  }, [handleMessage]);

  // Handle cell code change with debouncing
  const handleCellChange = useCallback((cellId: string, newCode: string) => {
    // Update local state immediately (optimistic UI)
    setCells((prev) =>
      prev.map((c) => (c.id === cellId ? { ...c, code: newCode } : c))
    );

    // Clear existing debounce timer for this cell
    const existingTimer = debounceTimersRef.current.get(cellId);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // Set new debounce timer (500ms delay)
    const timer = setTimeout(() => {
      wsRef.current?.send({
        type: 'cell_updated',
        cell_id: cellId,
        code: newCode,
      });
      debounceTimersRef.current.delete(cellId);
    }, 500);

    debounceTimersRef.current.set(cellId, timer);
  }, []);

  // Handle cell deletion
  const handleCellDelete = useCallback((cellId: string) => {
    // Clear any pending debounce timer
    const timer = debounceTimersRef.current.get(cellId);
    if (timer) {
      clearTimeout(timer);
      debounceTimersRef.current.delete(cellId);
    }

    wsRef.current?.send({
      type: 'delete_cell',
      cell_id: cellId,
    });
  }, []);

  // Handle manual cell execution
  const handleCellExecute = useCallback((cellId: string) => {
    // Clear any pending debounce timer and execute immediately
    const timer = debounceTimersRef.current.get(cellId);
    if (timer) {
      clearTimeout(timer);
      debounceTimersRef.current.delete(cellId);
    }

    // Find the current code for this cell
    const cell = cells.find((c) => c.id === cellId);
    if (cell) {
      wsRef.current?.send({
        type: 'cell_updated',
        cell_id: cellId,
        code: cell.code,
      });
    }
  }, [cells]);

  // Add new cell
  const handleAddCell = useCallback(() => {
    wsRef.current?.send({
      type: 'add_cell',
      position: cells.length,
    });
  }, [cells.length]);

  // Handle global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + Enter to add new cell
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleAddCell();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleAddCell]);

  return (
    <div className="app">
      <header className="header">
        <h1>Reactive Notebook</h1>
        <div className="connection-status">
          <div className={`connection-dot ${connected ? 'connected' : ''}`} />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </header>

      <div className="notebook">
        {cells.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📓</div>
            <h2>No cells yet</h2>
            <p>
              Click the button below to add your first Python cell. Edit any cell
              and watch dependent cells automatically re-run!
            </p>
            <button className="add-cell-btn" onClick={handleAddCell}>
              <span>+</span> Add Cell
            </button>
          </div>
        ) : (
          <>
            {cells.map((cell, index) => (
              <Cell
                key={cell.id}
                cell={cell}
                cellNumber={index + 1}
                onChange={handleCellChange}
                onDelete={handleCellDelete}
                onExecute={handleCellExecute}
              />
            ))}
            <div className="add-cell-container">
              <button className="add-cell-btn" onClick={handleAddCell}>
                <span>+</span> Add Cell
              </button>
            </div>
          </>
        )}
      </div>

      <div className="shortcuts-hint">
        <kbd>Shift</kbd> + <kbd>Enter</kbd> Run cell &nbsp;|&nbsp;
        <kbd>⌘</kbd> + <kbd>Enter</kbd> Add cell
      </div>
    </div>
  );
}

export default App;

