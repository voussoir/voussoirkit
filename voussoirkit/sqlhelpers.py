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
    query = 'DELETE FROM table %s' % qmarks
    cur.execute(query, bindings)
    '''
    qmarks = []
    bindings = []
    for (key, value) in pairs.items():
        qmarks.append('%s = ?' % key)
        bindings.append(value)
    qmarks = ' AND '.join(qmarks)
    qmarks = 'WHERE %s' % qmarks
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
    query = 'INSERT INTO table VALUES(%s)' % qmarks
    cur.execute(query, bindings)
    '''
    values = values.copy()
    for column in column_names:
        if column in values:
            continue
        if require_all:
            raise ValueError('Missing column "%s"' % column)
        else:
            values[column] = None
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
    query = 'UPDATE table %s' % qmarks
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
        qmarks.append('%s = ?' % key)
        bindings.append(value)
    bindings.append(where_value)
    setters = ', '.join(qmarks)
    qmarks = 'SET {setters} WHERE {where_key} == ?'
    qmarks = qmarks.format(setters=setters, where_key=where_key)
    return (qmarks, bindings)
