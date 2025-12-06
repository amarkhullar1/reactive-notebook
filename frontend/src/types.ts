/**
 * TypeScript interfaces for the reactive notebook
 */

export type CellStatus = 'idle' | 'running' | 'success' | 'error';

export interface Cell {
  id: string;
  code: string;
  output: string;
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

