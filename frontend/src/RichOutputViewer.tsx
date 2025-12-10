import type { RichOutput } from './types';

interface RichOutputViewerProps {
  data: RichOutput;
}

/**
 * Formats a cell value for display.
 * Handles special values like NaN, Infinity, null, etc.
 */
function formatCellValue(value: any): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (value === 'NaN') {
    return 'NaN';
  }
  if (value === 'Infinity') {
    return '∞';
  }
  if (value === '-Infinity') {
    return '-∞';
  }
  if (typeof value === 'number') {
    // Format numbers nicely
    if (Number.isInteger(value)) {
      return value.toLocaleString();
    }
    // Limit decimal places for floats
    return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  }
  if (typeof value === 'boolean') {
    return value ? 'True' : 'False';
  }
  if (typeof value === 'string') {
    // Truncate long strings
    return value.length > 50 ? value.slice(0, 47) + '...' : value;
  }
  return String(value);
}

/**
 * Renders a pandas DataFrame as a styled table.
 */
function DataFrameViewer({ data }: { data: RichOutput }) {
  const { columns = [], shape, truncated, index } = data;
  const rows = data.data as Record<string, any>[];

  return (
    <div className="rich-output dataframe-viewer">
      <div className="rich-output-header">
        <span className="rich-output-type">DataFrame</span>
        <span className="rich-output-shape">
          {shape[0].toLocaleString()} rows × {shape[1]} columns
          {truncated && <span className="truncated-badge">truncated</span>}
        </span>
      </div>
      <div className="dataframe-table-wrapper">
        <table className="dataframe-table">
          <thead>
            <tr>
              <th className="index-header">#</th>
              {columns.map((col) => (
                <th key={col} title={data.dtypes?.[col]}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="index-cell">{index ? formatCellValue(index[i]) : i}</td>
                {columns.map((col) => (
                  <td key={col} className={getCellClassName(row[col])}>
                    {formatCellValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="truncated-notice">
          Showing first 100 of {shape[0].toLocaleString()} rows
        </div>
      )}
    </div>
  );
}

/**
 * Renders a pandas Series as a styled table.
 */
function SeriesViewer({ data }: { data: RichOutput }) {
  const { name, shape, truncated, index } = data;
  const values = data.data as Record<string, any>;
  const entries = Object.entries(values);

  return (
    <div className="rich-output series-viewer">
      <div className="rich-output-header">
        <span className="rich-output-type">Series{name ? `: ${name}` : ''}</span>
        <span className="rich-output-shape">
          {shape[0].toLocaleString()} elements
          {truncated && <span className="truncated-badge">truncated</span>}
        </span>
      </div>
      <div className="dataframe-table-wrapper">
        <table className="dataframe-table series-table">
          <thead>
            <tr>
              <th className="index-header">Index</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value], i) => (
              <tr key={i}>
                <td className="index-cell">{formatCellValue(index?.[i] ?? key)}</td>
                <td className={getCellClassName(value)}>{formatCellValue(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="truncated-notice">
          Showing first 100 of {shape[0].toLocaleString()} elements
        </div>
      )}
    </div>
  );
}

/**
 * Renders a numpy ndarray.
 */
function NdarrayViewer({ data }: { data: RichOutput }) {
  const { shape, truncated, dtype } = data;
  const arrayData = data.data;

  // Check if 2D array
  const is2D = Array.isArray(arrayData[0]);

  return (
    <div className="rich-output ndarray-viewer">
      <div className="rich-output-header">
        <span className="rich-output-type">ndarray</span>
        <span className="rich-output-shape">
          shape=({shape.join(', ')}) dtype={dtype}
          {truncated && <span className="truncated-badge">truncated</span>}
        </span>
      </div>
      {is2D ? (
        <div className="dataframe-table-wrapper">
          <table className="dataframe-table ndarray-table">
            <thead>
              <tr>
                <th className="index-header">#</th>
                {(arrayData[0] as any[]).map((_, colIdx) => (
                  <th key={colIdx}>[{colIdx}]</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(arrayData as any[][]).map((row, rowIdx) => (
                <tr key={rowIdx}>
                  <td className="index-cell">{rowIdx}</td>
                  {row.map((val, colIdx) => (
                    <td key={colIdx} className={getCellClassName(val)}>
                      {formatCellValue(val)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="ndarray-1d">
          <code>
            [{(arrayData as any[]).slice(0, 20).map(formatCellValue).join(', ')}
            {(arrayData as any[]).length > 20 ? ', ...' : ''}]
          </code>
        </div>
      )}
      {truncated && (
        <div className="truncated-notice">
          Array truncated for display
        </div>
      )}
    </div>
  );
}

/**
 * Returns a CSS class based on the cell value type.
 */
function getCellClassName(value: any): string {
  if (value === null || value === undefined || value === 'NaN') {
    return 'cell-null';
  }
  if (typeof value === 'number' || value === 'Infinity' || value === '-Infinity') {
    return 'cell-number';
  }
  if (typeof value === 'boolean') {
    return 'cell-boolean';
  }
  return 'cell-string';
}

/**
 * Main component that routes to the appropriate viewer based on rich output type.
 */
export function RichOutputViewer({ data }: RichOutputViewerProps) {
  switch (data.type) {
    case 'dataframe':
      return <DataFrameViewer data={data} />;
    case 'series':
      return <SeriesViewer data={data} />;
    case 'ndarray':
      return <NdarrayViewer data={data} />;
    default:
      return <pre className="output-content">{JSON.stringify(data, null, 2)}</pre>;
  }
}

export default RichOutputViewer;
