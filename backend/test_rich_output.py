"""Tests for rich output serialization (DataFrames, arrays, etc.)."""
import pytest
import math

from kernel import (
    serialize_rich_output, 
    _safe_value, 
    _convert_to_safe_list,
    NotebookKernel,
    HAS_NUMPY,
    HAS_PANDAS,
    MAX_ROWS,
    MAX_ARRAY_ELEMENTS,
)

# Skip tests if libraries not available
pytestmark_numpy = pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
pytestmark_pandas = pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")

if HAS_NUMPY:
    import numpy as np
if HAS_PANDAS:
    import pandas as pd


class TestSafeValue:
    """Tests for _safe_value helper function."""
    
    def test_none(self):
        assert _safe_value(None) is None
    
    def test_regular_values(self):
        assert _safe_value(42) == 42
        assert _safe_value(3.14) == 3.14
        assert _safe_value("hello") == "hello"
        assert _safe_value(True) is True
    
    def test_nan(self):
        assert _safe_value(float('nan')) == "NaN"
    
    def test_infinity(self):
        assert _safe_value(float('inf')) == "Infinity"
        assert _safe_value(float('-inf')) == "-Infinity"
    
    @pytestmark_numpy
    def test_numpy_types(self):
        assert _safe_value(np.int64(42)) == 42
        assert _safe_value(np.float64(3.14)) == 3.14
        assert _safe_value(np.bool_(True)) is True
        assert _safe_value(np.nan) == "NaN"
    
    @pytestmark_pandas
    def test_pandas_na(self):
        assert _safe_value(pd.NA) is None
        assert _safe_value(pd.NaT) is None


class TestConvertToSafeList:
    """Tests for _convert_to_safe_list helper function."""
    
    def test_simple_list(self):
        result = _convert_to_safe_list([1, 2, 3])
        assert result == [1, 2, 3]
    
    def test_nested_list(self):
        result = _convert_to_safe_list([[1, 2], [3, 4]])
        assert result == [[1, 2], [3, 4]]
    
    def test_list_with_nan(self):
        result = _convert_to_safe_list([1, float('nan'), 3])
        assert result == [1, "NaN", 3]
    
    def test_list_of_dicts(self):
        result = _convert_to_safe_list([{"a": 1, "b": float('nan')}])
        assert result == [{"a": 1, "b": "NaN"}]


@pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
class TestSerializeDataFrame:
    """Tests for DataFrame serialization."""
    
    def test_simple_dataframe(self):
        df = pd.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35],
            'salary': [50000.0, 60000.0, 70000.0]
        })
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert result['type'] == 'dataframe'
        assert result['shape'] == [3, 3]
        assert result['columns'] == ['name', 'age', 'salary']
        assert result['truncated'] is False
        assert len(result['data']) == 3
        assert result['data'][0] == {'name': 'Alice', 'age': 25, 'salary': 50000.0}
    
    def test_dataframe_with_nan(self):
        df = pd.DataFrame({
            'a': [1.0, float('nan'), 3.0],
            'b': [4.0, 5.0, float('nan')]
        })
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert result['data'][1]['a'] == "NaN"
        assert result['data'][2]['b'] == "NaN"
    
    def test_dataframe_truncation(self):
        # Create DataFrame larger than MAX_ROWS
        df = pd.DataFrame({'x': range(MAX_ROWS + 50)})
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert result['truncated'] is True
        assert result['shape'] == [MAX_ROWS + 50, 1]
        assert len(result['data']) == MAX_ROWS
    
    def test_dataframe_dtypes(self):
        df = pd.DataFrame({
            'int_col': [1, 2, 3],
            'float_col': [1.0, 2.0, 3.0],
            'str_col': ['a', 'b', 'c']
        })
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert 'int' in result['dtypes']['int_col']
        assert 'float' in result['dtypes']['float_col']
        assert 'object' in result['dtypes']['str_col']
    
    def test_dataframe_with_index(self):
        df = pd.DataFrame(
            {'value': [10, 20, 30]},
            index=['a', 'b', 'c']
        )
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert result['index'] == ['a', 'b', 'c']
    
    def test_empty_dataframe(self):
        df = pd.DataFrame()
        
        result = serialize_rich_output(df)
        
        assert result is not None
        assert result['type'] == 'dataframe'
        assert result['shape'] == [0, 0]
        assert result['data'] == []


@pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
class TestSerializeSeries:
    """Tests for Series serialization."""
    
    def test_simple_series(self):
        s = pd.Series([1, 2, 3], name='numbers')
        
        result = serialize_rich_output(s)
        
        assert result is not None
        assert result['type'] == 'series'
        assert result['name'] == 'numbers'
        assert result['shape'] == [3]
        assert result['truncated'] is False
    
    def test_series_with_index(self):
        s = pd.Series([10, 20, 30], index=['a', 'b', 'c'])
        
        result = serialize_rich_output(s)
        
        assert result is not None
        assert result['data'] == {'a': 10, 'b': 20, 'c': 30}
        assert result['index'] == ['a', 'b', 'c']
    
    def test_series_truncation(self):
        s = pd.Series(range(MAX_ROWS + 50))
        
        result = serialize_rich_output(s)
        
        assert result is not None
        assert result['truncated'] is True
        assert result['shape'] == [MAX_ROWS + 50]
        assert len(result['data']) == MAX_ROWS


@pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
class TestSerializeNdarray:
    """Tests for numpy array serialization."""
    
    def test_1d_array(self):
        arr = np.array([1, 2, 3, 4, 5])
        
        result = serialize_rich_output(arr)
        
        assert result is not None
        assert result['type'] == 'ndarray'
        assert result['shape'] == [5]
        assert result['data'] == [1, 2, 3, 4, 5]
        assert result['truncated'] is False
    
    def test_2d_array(self):
        arr = np.array([[1, 2, 3], [4, 5, 6]])
        
        result = serialize_rich_output(arr)
        
        assert result is not None
        assert result['type'] == 'ndarray'
        assert result['shape'] == [2, 3]
        assert result['data'] == [[1, 2, 3], [4, 5, 6]]
    
    def test_array_with_nan(self):
        arr = np.array([1.0, np.nan, 3.0])
        
        result = serialize_rich_output(arr)
        
        assert result is not None
        assert result['data'] == [1.0, "NaN", 3.0]
    
    def test_array_truncation(self):
        arr = np.arange(MAX_ARRAY_ELEMENTS + 500)
        
        result = serialize_rich_output(arr)
        
        assert result is not None
        assert result['truncated'] is True
        assert result['shape'] == [MAX_ARRAY_ELEMENTS + 500]
        assert len(result['data']) == MAX_ARRAY_ELEMENTS
    
    def test_array_dtype(self):
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        
        result = serialize_rich_output(arr)
        
        assert result is not None
        assert 'float32' in result['dtype']


class TestSerializeNonRichTypes:
    """Tests that non-rich types return None."""
    
    def test_none(self):
        assert serialize_rich_output(None) is None
    
    def test_string(self):
        assert serialize_rich_output("hello") is None
    
    def test_number(self):
        assert serialize_rich_output(42) is None
        assert serialize_rich_output(3.14) is None
    
    def test_list(self):
        assert serialize_rich_output([1, 2, 3]) is None
    
    def test_dict(self):
        assert serialize_rich_output({'a': 1}) is None


@pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
class TestKernelDataFrameExecution:
    """Integration tests for kernel execution with DataFrames."""
    
    def test_execute_dataframe_creation(self):
        kernel = NotebookKernel()
        
        result = kernel.execute_cell(
            "test-1",
            "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})\ndf"
        )
        
        assert result['status'] == 'success'
        assert result['rich_output'] is not None
        assert result['rich_output']['type'] == 'dataframe'
        assert result['rich_output']['shape'] == [2, 2]
    
    def test_execute_series_creation(self):
        kernel = NotebookKernel()
        
        result = kernel.execute_cell(
            "test-1",
            "import pandas as pd\npd.Series([1, 2, 3], name='test')"
        )
        
        assert result['status'] == 'success'
        assert result['rich_output'] is not None
        assert result['rich_output']['type'] == 'series'
        assert result['rich_output']['name'] == 'test'
    
    def test_execute_no_rich_output_for_print(self):
        kernel = NotebookKernel()
        
        result = kernel.execute_cell(
            "test-1",
            "import pandas as pd\ndf = pd.DataFrame({'a': [1]})\nprint('hello')"
        )
        
        assert result['status'] == 'success'
        assert result['rich_output'] is None  # print() returns None
        assert 'hello' in result['output']


@pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
class TestKernelNumpyExecution:
    """Integration tests for kernel execution with numpy arrays."""
    
    def test_execute_array_creation(self):
        kernel = NotebookKernel()
        
        result = kernel.execute_cell(
            "test-1",
            "import numpy as np\nnp.array([1, 2, 3, 4, 5])"
        )
        
        assert result['status'] == 'success'
        assert result['rich_output'] is not None
        assert result['rich_output']['type'] == 'ndarray'
        assert result['rich_output']['shape'] == [5]
    
    def test_execute_2d_array(self):
        kernel = NotebookKernel()
        
        result = kernel.execute_cell(
            "test-1",
            "import numpy as np\nnp.array([[1, 2], [3, 4]])"
        )
        
        assert result['status'] == 'success'
        assert result['rich_output'] is not None
        assert result['rich_output']['shape'] == [2, 2]
