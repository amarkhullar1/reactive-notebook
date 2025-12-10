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

// Frontend → Backend Messages

export interface CellUpdatedMessage {
  type: 'cell_updated';
  cell_id: string;
  code: string;
}

export interface ExecuteCellMessage {
  type: 'execute_cell';
  cell_id: string;
}

export interface AddCellMessage {
  type: 'add_cell';
  position: number;
}

export interface DeleteCellMessage {
  type: 'delete_cell';
  cell_id: string;
}

export type ClientMessage = 
  | CellUpdatedMessage 
  | ExecuteCellMessage 
  | AddCellMessage 
  | DeleteCellMessage;

// Backend → Frontend Messages

export interface NotebookStateMessage {
  type: 'notebook_state';
  cells: Cell[];
}

export interface CellAddedMessage {
  type: 'cell_added';
  cell: Cell;
  position: number;
}

export interface CellDeletedMessage {
  type: 'cell_deleted';
  cell_id: string;
}

export interface ExecutionStartedMessage {
  type: 'execution_started';
  cell_id: string;
}

export interface ExecutionResultMessage {
  type: 'execution_result';
  cell_id: string;
  status: CellStatus;
  output: string;
  rich_output?: RichOutput | null;
  error: string;
}

export interface ExecutionQueueMessage {
  type: 'execution_queue';
  cell_ids: string[];
}

export interface ErrorMessage {
  type: 'error';
  cell_id?: string;
  message: string;
}

export type ServerMessage = 
  | NotebookStateMessage 
  | CellAddedMessage 
  | CellDeletedMessage 
  | ExecutionStartedMessage 
  | ExecutionResultMessage 
  | ExecutionQueueMessage
  | ErrorMessage;

