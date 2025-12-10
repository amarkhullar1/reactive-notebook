/**
 * TypeScript interfaces for the reactive notebook
 */

export type CellStatus = 'idle' | 'running' | 'success' | 'error';

export type RichOutputType = 'dataframe' | 'series' | 'ndarray';

export interface RichOutput {
  type: RichOutputType;
  data: any;  // Array of records for DataFrame, dict for Series, array for ndarray
  columns?: string[];  // Column names for DataFrame
  dtypes?: Record<string, string>;  // Data types per column
  dtype?: string;  // Single dtype for Series or ndarray
  index?: any[];  // Index values
  name?: string | null;  // Series name
  shape: number[];  // Shape of the data
  truncated: boolean;  // Whether data was truncated
}

export interface Cell {
  id: string;
  code: string;
  output: string;
  rich_output?: RichOutput | null;  // Structured output for DataFrames etc.
  error: string;
  status: CellStatus;
}

export interface NotebookMetadata {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

// Frontend → Backend Messages

export interface CellUpdatedMessage {
  type: 'cell_updated';
  notebook_id: string;
  cell_id: string;
  code: string;
}

export interface ExecuteCellMessage {
  type: 'execute_cell';
  notebook_id: string;
  cell_id: string;
}

export interface AddCellMessage {
  type: 'add_cell';
  notebook_id: string;
  position: number;
}

export interface DeleteCellMessage {
  type: 'delete_cell';
  notebook_id: string;
  cell_id: string;
}

export interface InterruptMessage {
  type: 'interrupt';
  notebook_id: string;
}

// Notebook management messages (Frontend → Backend)

export interface ListNotebooksMessage {
  type: 'list_notebooks';
}

export interface CreateNotebookMessage {
  type: 'create_notebook';
  name: string;
}

export interface DeleteNotebookMessage {
  type: 'delete_notebook';
  notebook_id: string;
}

export interface RenameNotebookMessage {
  type: 'rename_notebook';
  notebook_id: string;
  name: string;
}

export interface OpenNotebookMessage {
  type: 'open_notebook';
  notebook_id: string;
}

export type ClientMessage = 
  | CellUpdatedMessage 
  | ExecuteCellMessage 
  | AddCellMessage 
  | DeleteCellMessage
  | InterruptMessage
  | ListNotebooksMessage
  | CreateNotebookMessage
  | DeleteNotebookMessage
  | RenameNotebookMessage
  | OpenNotebookMessage;

// Backend → Frontend Messages

export interface NotebookStateMessage {
  type: 'notebook_state';
  notebook_id: string;
  notebook_name: string;
  cells: Cell[];
}

export interface NotebooksListMessage {
  type: 'notebooks_list';
  notebooks: NotebookMetadata[];
  active_notebook_id?: string | null;
}

export interface NotebookCreatedMessage {
  type: 'notebook_created';
  notebook: NotebookMetadata;
}

export interface NotebookDeletedMessage {
  type: 'notebook_deleted';
  notebook_id: string;
}

export interface NotebookRenamedMessage {
  type: 'notebook_renamed';
  notebook_id: string;
  name: string;
}

export interface CellAddedMessage {
  type: 'cell_added';
  notebook_id: string;
  cell: Cell;
  position: number;
}

export interface CellDeletedMessage {
  type: 'cell_deleted';
  notebook_id: string;
  cell_id: string;
}

export interface ExecutionStartedMessage {
  type: 'execution_started';
  notebook_id: string;
  cell_id: string;
}

export interface ExecutionResultMessage {
  type: 'execution_result';
  notebook_id: string;
  cell_id: string;
  status: CellStatus;
  output: string;
  rich_output?: RichOutput | null;
  error: string;
}

export interface ExecutionQueueMessage {
  type: 'execution_queue';
  notebook_id: string;
  cell_ids: string[];
}

export interface ExecutionInterruptedMessage {
  type: 'execution_interrupted';
  notebook_id: string;
  cell_id?: string;
  message: string;
}

export interface ErrorMessage {
  type: 'error';
  notebook_id?: string;
  cell_id?: string;
  message: string;
}

export type ServerMessage = 
  | NotebookStateMessage 
  | NotebooksListMessage
  | NotebookCreatedMessage
  | NotebookDeletedMessage
  | NotebookRenamedMessage
  | CellAddedMessage 
  | CellDeletedMessage 
  | ExecutionStartedMessage 
  | ExecutionResultMessage 
  | ExecutionQueueMessage
  | ExecutionInterruptedMessage
  | ErrorMessage;
