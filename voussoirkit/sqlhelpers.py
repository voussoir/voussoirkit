import re
import types

def delete_filler(pairs):
    '''
    Manually aligning the bindings for DELETE statements is annoying.
    Given a dictionary of {column: value}, return the "WHERE ..." portion of
    the query and the bindings in the correct order.

    Example:
    pairs={'test': 'toast', 'ping': 'pong'}
    ->
    returns ('WHERE test = ? AND ping = ?', ['toast', 'pong'])

    In context:
    (qmarks, bindings) = delete_filler(pairs)
    query = f'DELETE FROM table {qmarks}'
    cur.execute(query, bindings)
    '''
    qmarks = []
    bindings = []
    for (key, value) in pairs.items():
        qmarks.append(f'{key} = ?')
        bindings.append(value)
    qmarks = ' AND '.join(qmarks)
    qmarks = f'WHERE {qmarks}'
    return (qmarks, bindings)

def insert_filler(column_names, values, require_all=True):
    '''
    Manually aligning the bindings for INSERT statements is annoying.
    Given the table's column names and a dictionary of {column: value},
    return the question marks and the list of bindings in the right order.

    require_all:
        If `values` does not contain one of the column names, should we raise
        an exception?
        Otherwise, that column will simply receive None.

    Example:
    column_names=['id', 'name', 'score'],
    values={'score': 20, 'id': '1111', 'name': 'James'}
    ->
    returns ('?, ?, ?', ['1111', 'James', 20])

    In context:
    (qmarks, bindings) = insert_filler(COLUMN_NAMES, data)
    query = f'INSERT INTO table VALUES({qmarks})'
    cur.execute(query, bindings)
    '''
    values = values.copy()
    missings = []
    for column in column_names:
        if column in values:
            continue
        if require_all:
            missings.append(column)
        else:
            values[column] = None
    if missings:
        raise ValueError(f'Missing columns {missings}.')
    qmarks = '?' * len(column_names)
    qmarks = ', '.join(qmarks)
    bindings = [values[column] for column in column_names]
    return (qmarks, bindings)

def update_filler(pairs, where_key):
    '''
    Manually aligning the bindings for UPDATE statements is annoying.
    Given a dictionary of {column: value} as well as the name of the column
    to be used as the WHERE, return the "SET ..." portion of the query and the
    bindings in the correct order.

    If the where_key needs to be reassigned also, let its value be a 2-tuple
    where [0] is the current value used for WHERE, and [1] is the new value
    used for SET.

    Example:
    pairs={'id': '1111', 'name': 'James', 'score': 20},
    where_key='id'
    ->
    returns ('SET name = ?, score = ? WHERE id == ?', ['James', 20, '1111'])

    Example:
    pairs={'filepath': ('/oldplace', '/newplace')},
    where_key='filepath'
    ->
    returns ('SET filepath = ? WHERE filepath == ?', ['/newplace', '/oldplace'])

    In context:
    (qmarks, bindings) = update_filler(data, where_key)
    query = f'UPDATE table {qmarks}'
    cur.execute(query, bindings)
    '''
    pairs = pairs.copy()
    where_value = pairs.pop(where_key)
    if isinstance(where_value, tuple):
        (where_value, pairs[where_key]) = where_value
    if isinstance(where_value, dict):
        where_value = where_value['old']
        pairs[where_key] = where_value['new']

    if len(pairs) == 0:
        raise ValueError('No pairs left after where_key.')

    qmarks = []
    bindings = []
    for (key, value) in pairs.items():
        qmarks.append(f'{key} = ?')
        bindings.append(value)
    bindings.append(where_value)
    setters = ', '.join(qmarks)
    qmarks = 'SET {setters} WHERE {where_key} == ?'
    qmarks = qmarks.format(setters=setters, where_key=where_key)
    return (qmarks, bindings)

def hex_byte(byte):
    '''
    Return the hex string for this byte. 00-ff.
    '''
    if byte not in range(0, 256):
        raise ValueError(byte)
    return hex(byte)[2:].rjust(2, '0')

def literal(item):
    '''
    Return a string depicting the SQL literal for this item.

    Example:
    0 -> "0"
    'hello' -> "'hello'"
    b'hello' -> "X'68656c6c6f'"
    [3, 'hi'] -> "(3, 'hi')"
    '''
    if item is None:
        return 'NULL'

    elif isinstance(item, bool):
        return f'{int(item)}'

    elif isinstance(item, int):
        return f'{item}'

    elif isinstance(item, float):
        return f'{item:f}'

    elif isinstance(item, str):
        item = item.replace("'", "''")
        return f"'{item}'"

    elif isinstance(item, bytes):
        item = ''.join(hex_byte(byte) for byte in item)
        return f"X'{item}'"

    elif isinstance(item, (list, tuple, set, types.GeneratorType)):
        return listify(item)

    else:
        raise ValueError(f'Unrecognized type {type(item)} {item}.')

def listify(items):
    output = ', '.join(literal(item) for item in items)
    output = f'({output})'
    return output

def _extract_create_table_statements(script):
    # script = sqlparse.format(script, strip_comments=True)
    # script = re.sub(r'\s*--.+$', '', script, flags=re.MULTILINE)
    script = re.sub(r'\n\s*create ', ';\ncreate ', script, flags=re.IGNORECASE)
    for statement in script.split(';'):
        statement = statement.strip()
        if statement.lower().startswith('create table'):
            yield statement

def _extract_table_name(create_table_statement):
    # CREATE TABLE table_name(...)
    table_name = create_table_statement.split('(')[0].strip()
    table_name = table_name.split()[-1]
    return table_name

def _extract_columns_from_table(create_table_statement):
    # CREATE TABLE table_name(column_name TYPE MODIFIERS, ...)
    constraints = {'constraint', 'foreign', 'check', 'primary', 'unique'}
    column_names = create_table_statement.split('(')[1].rsplit(')', 1)[0]
    column_names = column_names.split(',')
    column_names = [x.strip() for x in column_names]
    column_names = [x.split(' ')[0] for x in column_names]
    column_names = [c for c in column_names if c.lower() not in constraints]
    return column_names

def _reverse_index(columns):
    return {column: index for (index, column) in enumerate(columns)}

def extract_table_column_map(script):
    '''
    Given an entire SQL script containing CREATE TABLE statements, return a
    dictionary of the form
    {
        'table1': [
            'column1',
            'column2',
        ],
        'table2': [
            'column1',
            'column2',
        ],
    }
    '''
    columns = {}
    create_table_statements = _extract_create_table_statements(script)
    for create_table_statement in create_table_statements:
        table_name = _extract_table_name(create_table_statement)
        columns[table_name] = _extract_columns_from_table(create_table_statement)
    return columns

def reverse_table_column_map(table_column_map):
    '''
    Given the table column map, return a reversed version of the form
    {
        'table1': {
            'column1': 0,
            'column2': 1,
        },
        'table2': {
            'column1': 0,
            'column2': 1,
        },
    }
    If you have a row of data and you want to access one of the columns, you can
    use this map to figure out which tuple index corresponds to the column name.
    For example:
        row = ('abcd', 'John', 23)
        index = INDEX['people']['name']
        print(row[index])
    '''
    return {table: _reverse_index(columns) for (table, columns) in table_column_map.items()}
