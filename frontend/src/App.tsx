import { useState, useEffect, useRef, useCallback } from 'react';
import { Cell } from './Cell';
import { createWebSocketClient, type WebSocketClient } from './websocket';
import type { Cell as CellType, ServerMessage, NotebookMetadata } from './types';

function App() {
  const [cells, setCells] = useState<CellType[]>([]);
  const [notebooks, setNotebooks] = useState<NotebookMetadata[]>([]);
  const [activeNotebookId, setActiveNotebookId] = useState<string | null>(null);
  const [activeNotebookName, setActiveNotebookName] = useState<string>('');
  const [connected, setConnected] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [editingNotebookId, setEditingNotebookId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const wsRef = useRef<WebSocketClient | null>(null);
  const debounceTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Handle incoming WebSocket messages
  const handleMessage = useCallback((message: ServerMessage) => {
    switch (message.type) {
      case 'notebooks_list':
        setNotebooks(message.notebooks);
        if (message.active_notebook_id) {
          setActiveNotebookId(message.active_notebook_id);
        }
        break;

      case 'notebook_state':
        setActiveNotebookId(message.notebook_id);
        setActiveNotebookName(message.notebook_name);
        setCells(message.cells);
        break;

      case 'notebook_created':
        setNotebooks((prev) => [message.notebook, ...prev]);
        break;

      case 'notebook_deleted':
        setNotebooks((prev) => prev.filter((n) => n.id !== message.notebook_id));
        // If the deleted notebook was active, clear cells
        if (activeNotebookId === message.notebook_id) {
          setCells([]);
          setActiveNotebookId(null);
          setActiveNotebookName('');
        }
        break;

      case 'notebook_renamed':
        setNotebooks((prev) =>
          prev.map((n) =>
            n.id === message.notebook_id ? { ...n, name: message.name } : n
          )
        );
        if (activeNotebookId === message.notebook_id) {
          setActiveNotebookName(message.name);
        }
        break;

      case 'cell_added':
        // Only update if this is for the active notebook
        if (message.notebook_id === activeNotebookId) {
          setCells((prev) => {
            const newCells = [...prev];
            newCells.splice(message.position, 0, message.cell);
            return newCells;
          });
        }
        break;

      case 'cell_deleted':
        if (message.notebook_id === activeNotebookId) {
          setCells((prev) => prev.filter((c) => c.id !== message.cell_id));
        }
        break;

      case 'execution_started':
        if (message.notebook_id === activeNotebookId) {
          setCells((prev) =>
            prev.map((c) =>
              c.id === message.cell_id ? { ...c, status: 'running' as const } : c
            )
          );
        }
        break;

      case 'execution_result':
        if (message.notebook_id === activeNotebookId) {
          setCells((prev) =>
            prev.map((c) =>
              c.id === message.cell_id
                ? {
                    ...c,
                    status: message.status,
                    output: message.output,
                    rich_output: message.rich_output,
                    error: message.error,
                  }
                : c
            )
          );
        }
        break;

      case 'execution_queue':
        if (message.notebook_id === activeNotebookId) {
          setCells((prev) =>
            prev.map((c) =>
              message.cell_ids.includes(c.id) && c.status !== 'running'
                ? { ...c, status: 'running' as const }
                : c
            )
          );
        }
        break;

      case 'execution_interrupted':
        if (message.notebook_id === activeNotebookId) {
          if (message.cell_id) {
            setCells((prev) =>
              prev.map((c) =>
                c.id === message.cell_id
                  ? { ...c, status: 'idle' as const, error: 'Interrupted' }
                  : c
              )
            );
          }
          setCells((prev) =>
            prev.map((c) =>
              c.status === 'running' ? { ...c, status: 'idle' as const } : c
            )
          );
        }
        break;

      case 'error':
        if (!message.notebook_id || message.notebook_id === activeNotebookId) {
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
        }
        break;
    }
  }, [activeNotebookId]);

  // Initialize WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    wsRef.current = createWebSocketClient(wsUrl, handleMessage, setConnected);

    return () => {
      wsRef.current?.close();
    };
  }, [handleMessage]);

  // Handle cell code change with debouncing
  const handleCellChange = useCallback((cellId: string, newCode: string) => {
    if (!activeNotebookId) return;

    setCells((prev) =>
      prev.map((c) => (c.id === cellId ? { ...c, code: newCode } : c))
    );

    const existingTimer = debounceTimersRef.current.get(cellId);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    const timer = setTimeout(() => {
      wsRef.current?.send({
        type: 'cell_updated',
        notebook_id: activeNotebookId,
        cell_id: cellId,
        code: newCode,
      });
      debounceTimersRef.current.delete(cellId);
    }, 500);

    debounceTimersRef.current.set(cellId, timer);
  }, [activeNotebookId]);

  // Handle cell deletion
  const handleCellDelete = useCallback((cellId: string) => {
    if (!activeNotebookId) return;

    const timer = debounceTimersRef.current.get(cellId);
    if (timer) {
      clearTimeout(timer);
      debounceTimersRef.current.delete(cellId);
    }

    wsRef.current?.send({
      type: 'delete_cell',
      notebook_id: activeNotebookId,
      cell_id: cellId,
    });
  }, [activeNotebookId]);

  // Handle manual cell execution
  const handleCellExecute = useCallback((cellId: string) => {
    if (!activeNotebookId) return;

    const timer = debounceTimersRef.current.get(cellId);
    if (timer) {
      clearTimeout(timer);
      debounceTimersRef.current.delete(cellId);
    }

    const cell = cells.find((c) => c.id === cellId);
    if (cell) {
      wsRef.current?.send({
        type: 'cell_updated',
        notebook_id: activeNotebookId,
        cell_id: cellId,
        code: cell.code,
      });
    }
  }, [activeNotebookId, cells]);

  // Handle interrupt
  const handleInterrupt = useCallback(() => {
    if (!activeNotebookId) return;
    wsRef.current?.send({
      type: 'interrupt',
      notebook_id: activeNotebookId,
    });
  }, [activeNotebookId]);

  // Add new cell
  const handleAddCell = useCallback(() => {
    if (!activeNotebookId) return;
    wsRef.current?.send({
      type: 'add_cell',
      notebook_id: activeNotebookId,
      position: cells.length,
    });
  }, [activeNotebookId, cells.length]);

  // Notebook management handlers
  const handleCreateNotebook = useCallback(() => {
    wsRef.current?.send({
      type: 'create_notebook',
      name: 'Untitled Notebook',
    });
  }, []);

  const handleOpenNotebook = useCallback((notebookId: string) => {
    wsRef.current?.send({
      type: 'open_notebook',
      notebook_id: notebookId,
    });
  }, []);

  const handleDeleteNotebook = useCallback((notebookId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this notebook?')) {
      wsRef.current?.send({
        type: 'delete_notebook',
        notebook_id: notebookId,
      });
    }
  }, []);

  const handleStartRename = useCallback((notebookId: string, currentName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingNotebookId(notebookId);
    setEditingName(currentName);
  }, []);

  const handleFinishRename = useCallback(() => {
    if (editingNotebookId && editingName.trim()) {
      wsRef.current?.send({
        type: 'rename_notebook',
        notebook_id: editingNotebookId,
        name: editingName.trim(),
      });
    }
    setEditingNotebookId(null);
    setEditingName('');
  }, [editingNotebookId, editingName]);

  const handleRenameKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleFinishRename();
    } else if (e.key === 'Escape') {
      setEditingNotebookId(null);
      setEditingName('');
    }
  }, [handleFinishRename]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleAddCell();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleAddCell]);

  const isAnyRunning = cells.some((c) => c.status === 'running');

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <h2>Notebooks</h2>
          <button
            className="btn btn-icon"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>
        
        {!sidebarCollapsed && (
          <>
            <button className="btn btn-new-notebook" onClick={handleCreateNotebook}>
              + New Notebook
            </button>
            
            <ul className="notebook-list">
              {notebooks.map((notebook) => (
                <li
                  key={notebook.id}
                  className={`notebook-item ${notebook.id === activeNotebookId ? 'active' : ''}`}
                  onClick={() => handleOpenNotebook(notebook.id)}
                >
                  {editingNotebookId === notebook.id ? (
                    <input
                      type="text"
                      className="notebook-rename-input"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onBlur={handleFinishRename}
                      onKeyDown={handleRenameKeyDown}
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                    />
                  ) : (
                    <>
                      <span className="notebook-name" title={notebook.name}>
                        {notebook.name}
                      </span>
                      <div className="notebook-actions">
                        <button
                          className="btn btn-icon btn-small"
                          onClick={(e) => handleStartRename(notebook.id, notebook.name, e)}
                          title="Rename"
                        >
                          ✎
                        </button>
                        <button
                          className="btn btn-icon btn-small btn-danger"
                          onClick={(e) => handleDeleteNotebook(notebook.id, e)}
                          title="Delete"
                        >
                          ×
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>

      {/* Main content */}
      <main className="main-content">
        <header className="header">
          <h1>{activeNotebookName || 'Reactive Notebook'}</h1>
          <div className="header-actions">
            {isAnyRunning && (
              <button 
                className="btn btn-stop-global"
                onClick={handleInterrupt}
                title="Stop all execution"
              >
                ■ Stop
              </button>
            )}
            <div className="connection-status">
              <div className={`connection-dot ${connected ? 'connected' : ''}`} />
              <span>{connected ? 'Connected' : 'Disconnected'}</span>
            </div>
          </div>
        </header>

        <div className="notebook">
          {!activeNotebookId ? (
            <div className="empty-state">
              <div className="empty-state-icon">📓</div>
              <h2>No notebook selected</h2>
              <p>
                Select a notebook from the sidebar or create a new one to get started.
              </p>
              <button className="add-cell-btn" onClick={handleCreateNotebook}>
                <span>+</span> New Notebook
              </button>
            </div>
          ) : cells.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📝</div>
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
                  onInterrupt={handleInterrupt}
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
      </main>
    </div>
  );
}

export default App;
