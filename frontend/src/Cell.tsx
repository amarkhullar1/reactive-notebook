import Editor from '@monaco-editor/react';
import type { Cell as CellType } from './types';
import { RichOutputViewer } from './RichOutputViewer';

interface CellProps {
  cell: CellType;
  cellNumber: number;
  onChange: (cellId: string, code: string) => void;
  onDelete: (cellId: string) => void;
  onExecute: (cellId: string) => void;
  onInterrupt: () => void;
}

export function Cell({ cell, cellNumber, onChange, onDelete, onExecute, onInterrupt }: CellProps) {
  const handleEditorChange = (value: string | undefined) => {
    onChange(cell.id, value || '');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Shift+Enter to execute
    if (e.shiftKey && e.key === 'Enter') {
      e.preventDefault();
      onExecute(cell.id);
    }
  };

  return (
    <div 
      className={`cell ${cell.status}`}
      onKeyDown={handleKeyDown}
    >
      <div className="cell-header">
        <div className="cell-info">
          <span className="cell-id">In [{cellNumber}]</span>
          <StatusIndicator status={cell.status} />
        </div>
        <div className="cell-actions">
          {cell.status === 'running' ? (
            <button 
              className="btn btn-icon btn-stop"
              onClick={onInterrupt}
              title="Stop execution"
            >
              ■
            </button>
          ) : (
            <button 
              className="btn btn-icon"
              onClick={() => onExecute(cell.id)}
              title="Run cell (Shift+Enter)"
            >
              ▶
            </button>
          )}
          <button 
            className="btn btn-icon btn-danger"
            onClick={() => {
              if (cell.status === 'running') {
                // If running, interrupt first then delete
                onInterrupt();
                // Small delay to let interrupt take effect
                setTimeout(() => onDelete(cell.id), 100);
              } else {
                onDelete(cell.id);
              }
            }}
            title={cell.status === 'running' ? 'Stop and delete cell' : 'Delete cell'}
          >
            ✕
          </button>
        </div>
      </div>
      
      <div className="code-editor-container">
        <Editor
          height="auto"
          defaultLanguage="python"
          path={`cell-${cell.id}.py`}
          value={cell.code}
          onChange={handleEditorChange}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            lineNumbersMinChars: 3,
            scrollBeyondLastLine: false,
            fontSize: 14,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            tabSize: 4,
            automaticLayout: true,
            wordWrap: 'on',
            padding: { top: 12, bottom: 12 },
            scrollbar: {
              vertical: 'hidden',
              horizontal: 'hidden',
            },
            overviewRulerLanes: 0,
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            renderLineHighlight: 'line',
            lineDecorationsWidth: 8,
            folding: false,
            glyphMargin: false,
          }}
          onMount={(editor) => {
            // Auto-resize editor based on content
            const updateHeight = () => {
              const contentHeight = Math.max(60, Math.min(400, editor.getContentHeight()));
              const container = editor.getContainerDomNode();
              container.style.height = `${contentHeight}px`;
              editor.layout();
            };
            editor.onDidContentSizeChange(updateHeight);
            updateHeight();
          }}
        />
      </div>
      
      <div className="cell-output">
        {cell.status === 'running' ? (
          <div className="running-indicator">
            <div className="spinner" />
            <span>Running...</span>
          </div>
        ) : (
          <>
            {cell.error && (
              <pre className="output-content output-error">{cell.error}</pre>
            )}
            {!cell.error && cell.rich_output && (
              <RichOutputViewer data={cell.rich_output} />
            )}
            {!cell.error && !cell.rich_output && cell.output && (
              <pre className="output-content">{cell.output}</pre>
            )}
            {!cell.output && !cell.error && !cell.rich_output && cell.status !== 'idle' && (
              <pre className="output-content"></pre>
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface StatusIndicatorProps {
  status: CellType['status'];
}

function StatusIndicator({ status }: StatusIndicatorProps) {
  const labels: Record<CellType['status'], string> = {
    idle: 'Idle',
    running: 'Running',
    success: 'Done',
    error: 'Error',
  };

  return (
    <div className={`status-indicator ${status}`}>
      <div className="status-dot" />
      <span>{labels[status]}</span>
    </div>
  );
}

export default Cell;

