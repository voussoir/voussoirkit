'''
sqlhelpers
==========

This module provides functions for SQL string manipulation that I need often.
Most importantly, creating the right number of ? for binding insert / update
statements.
'''
import functools
import re
import sqlite3
import types

from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

_CREATE_TABLE_PATTERN = re.compile(
    r'^(?P<head>(?:\s|--[^\n]*\n)*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)'
    r'(?P<name>"(?:[^"]|"")+"|`[^`]+`|\[[^\]]+\]|[^\s(]+)',
    flags=re.IGNORECASE,
)

class Inject:
    '''
    When making UPDATE or DELETE statements, you may wish to use WHERE clauses
    that are not simply data values, such as sqlite function calls. When making
    your pairs dict for update_filler or delete_filler, you can let the value of
    a pair be an Inject class with a string, and that string will be directly
    injected into the query.

    You should not use an Inject for any user-provided strings, but you could
    let the user pick between two different Injects prepared by you.

    >>> pairs = {
    ...     'domain': 'example.com',
    ...     'url': sqlhelpers.Inject('REPLACE(url, "http://", "https://")'),
    ... }
    >>> sqlhelpers.update_filler(pairs=pairs, where_key='domain')
    ('SET url = REPLACE(url, "http://", "https://") WHERE domain == ?', ['example.com'])
    '''
    def __init__(self, string):
        self.string = string

def delete_filler(pairs):
    '''
    Manually aligning the bindings for DELETE statements is annoying.
    Given a dictionary of {column: value}, return the "WHERE ..." portion of
    the query and the bindings in the correct order.

    >>> pairs={'test': 'toast', 'ping': 'pong'}
    >>> delete_filler(pairs)
    ('WHERE test == ? AND ping == ?', ['toast', 'pong'])

    In context:
    (qmarks, bindings) = delete_filler(pairs)
    query = f'DELETE FROM table {qmarks}'
    cur.execute(query, bindings)
    '''
    qmarks = []
    bindings = []
    for (key, value) in pairs.items():
        if isinstance(value, Inject):
            qmarks.append(f'{key} == {value.string}')
        else:
            qmarks.append(f'{key} == ?')
            bindings.append(value)
    qmarks = ' AND '.join(qmarks)
    qmarks = f'WHERE {qmarks}'
    return (qmarks, bindings)

def insert_filler(pairs):
    '''
    Manually aligning the bindings for INSERT statements is annoying.
    Given a dictionary of {column: value}, return the question marks and the
    list of bindings in the right order.

    >>> insert_filler({'score': 20, 'id': '1111', 'name': 'James'})
    ('(id, name, score) VALUES (?, ?, ?)', ['1111', 'James', 20])

    In context:
    (qmarks, bindings) = insert_filler(pairs)
    query = f'INSERT INTO table {qmarks}'
    cur.execute(query, bindings)
    '''
    column_names = []
    bindings = []
    for (key, value) in pairs.items():
        column_names.append(key)
        bindings.append(value)

    column_names = ', '.join(column_names)
    qmarks = '?' * len(pairs)
    qmarks = ', '.join(qmarks)
    qmarks = f'({column_names}) VALUES ({qmarks})'
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

    >>> pairs={'id': '1111', 'name': 'James', 'score': 20},
    >>> where_key='id'
    >>> update_filler(pairs, where_key)
    ('SET name = ?, score = ? WHERE id == ?', ['James', 20, '1111'])

    Example:
    >>> pairs={'filepath': ('/oldplace', '/newplace')},
    >>> where_key='filepath'
    >>> update_filler(pairs, where_key)
    ('SET filepath = ? WHERE filepath == ?', ['/newplace', '/oldplace'])

    In context:
    (qmarks, bindings) = update_filler(data, where_key)
    query = f'UPDATE table {qmarks}'
    cur.execute(query, bindings)
    '''
    pairs = pairs.copy()
    if isinstance(where_key, tuple):
        wheres = {k: pairs.pop(k) for k in where_key}
    else:
        wheres = {where_key: pairs.pop(where_key)}

    for (where_key, where_value) in wheres.items():
        if isinstance(where_value, tuple):
            (wheres[where_key], pairs[where_key]) = where_value
        if isinstance(where_value, dict):
            wheres[where_key] = where_value['old']
            pairs[where_key] = where_value['new']

    if len(pairs) == 0:
        raise ValueError('No pairs left after where_key.')

    qmarks = []
    bindings = []
    for (key, value) in pairs.items():
        if isinstance(value, Inject):
            qmarks.append(f'{key} = {value.string}')
        else:
            qmarks.append(f'{key} = ?')
            bindings.append(value)

    wheres = list(wheres.items())
    bindings.extend(value for (key, value) in wheres)
    wheres = ' AND '.join(f'{key} = ?' for (key, value) in wheres)
    setters = ', '.join(qmarks)
    qmarks = f'SET {setters} WHERE {wheres}'
    return (qmarks, bindings)

####################################################################################################

def _extract_create_table_name(create_table_statement):
    match = _CREATE_TABLE_PATTERN.match(create_table_statement)
    if not match:
        raise ValueError(f'Could not find the table name in {create_table_statement!r}.')
    return _unquote_identifier(match.group('name'))

def _quote_identifier(name):
    name = name.replace('"', '""')
    return f'"{name}"'

def _rename_create_table(create_table_statement, new_name):
    # Validates that there is a name to replace.
    _extract_create_table_name(create_table_statement)
    replacement = lambda match: match.group('head') + _quote_identifier(new_name)
    return _CREATE_TABLE_PATTERN.sub(replacement, create_table_statement, count=1)

def _unquote_identifier(name):
    if name[0] == '"' and name[-1] == '"':
        return name[1:-1].replace('""', '"')
    if (name[0], name[-1]) in {('`', '`'), ('[', ']')}:
        return name[1:-1]
    return name

def _remove_script_comments(script):
    lines = []
    for line in script.splitlines():
        if re.match(r'^\s*--', line):
            continue
        lines.append(line)
    return '\n'.join(lines)

def assert_user_version(connection, target_version):
    current_version = connection.execute('PRAGMA user_version').fetchone()[0]
    if current_version != target_version:
        raise ValueError(f'Database user_version {current_version} should be {target_version}.')

def executescript(conn, script):
    '''
    The problem with Python's default executescript is that it executes a
    commit before running your script. If I wanted a commit I'd write one!
    '''
    statements = split_statements(script)
    cur = conn.cursor()
    for statement in statements:
        cur.execute(statement)

def foreign_key_check(connection):
    violations = connection.execute('PRAGMA foreign_key_check').fetchall()
    if not violations:
        return

    text = ', '.join(
        f'{table} rowid {rowid} -> {parent}'
        for (table, rowid, parent, fkid) in violations[:10]
    )
    raise RuntimeError(f'Found {len(violations)} foreign key violations: {text}.')

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

    >>> literal(0)
    "0"

    >>> literal('hello')
    "'hello'"

    >>> literal(b'hello')
    "X'68656c6c6f'"

    >>> literal([3, 'hi'])
    "(3, 'hi')"
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

def rebuild_table(connection, table, create, select=None):
    '''
    Rebuild an existing table in a new format, for schema changes that ALTER
    TABLE can't make in place: adding a column somewhere other than the end,
    reordering columns, changing types or collations, adding constraints, etc.
    The rebuild happens immediately.

    This performs steps 3-8 of the procedure from
    https://www.sqlite.org/lang_altertable.html#making_other_kinds_of_table_schema_changes
    The new format is created under a temporary name, the data is copied in,
    the original table is dropped, and the new table is renamed to the real
    name. Because the new table is renamed *into* the real name, foreign keys
    and triggers on other tables that refer to it still point to the right
    place, so you only need to rebuild the tables you're actually changing.

    The opposite order, renaming the original to X_old first, is wrong: since
    SQLite 3.26, renaming a table also rewrites the references to it in other
    tables, so they would end up pointing at X_old, which is then dropped.

    The rest of the procedure (foreign keys off, BEGIN, foreign_key_check,
    COMMIT, foreign keys on) is handled for you if you call this inside a
    function decorated with @upgrader. Otherwise, you must do those yourself.
    This function raises RuntimeError if foreign keys are on or there is no
    transaction active.

    connection:
        An sqlite3.Connection.

    table:
        The name of the existing table.

    create:
        The CREATE TABLE statement for the new format, using the table's real
        name. The temporary name will be substituted in.

    select:
        A SELECT statement whose results fill the new table, reading from the
        existing table by its real name, like
        'SELECT id, title, NULL, author_id FROM albums'.
        The columns must line up with the new table, minus any generated
        columns. If omitted, uses SELECT * FROM table, which only works if the
        columns are the same as before, e.g. when only types or constraints
        changed.

    Indexes and triggers that belong to the table are recreated from their
    original SQL. If the schema change makes one of them invalid, like an index
    on a column you removed, drop it before calling this function and create
    its replacement afterward.

    Views are not touched. If a view refers to the table in a way that the
    change breaks, drop and recreate it yourself.

    After the rebuild, the CREATE TABLE text stored in sqlite_master will have
    the table name in double quotes, because that's how ALTER TABLE RENAME
    writes it. This is cosmetic.

    Example:
        @upgrader(from_version=18, to_version=19)
        def upgrade_18_to_19(connection):
            rebuild_table(
                connection,
                'photos',
                create='CREATE TABLE photos(id INT PRIMARY KEY, mtime INT, filepath TEXT)',
                select='SELECT id, NULL, filepath FROM photos',
            )
    '''
    def execute(query, bindings=[]):
        log.debug(query)
        return connection.execute(query, bindings)

    if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 0:
        raise RuntimeError('Foreign keys must be turned off before starting the transaction.')

    if not connection.in_transaction:
        raise RuntimeError('You must begin a transaction before rebuilding a table.')

    temp = f'rebuild_new_{table}'
    query = "SELECT name FROM sqlite_master WHERE type == 'table'"
    existing = {name.lower() for (name,) in execute(query).fetchall()}
    if table.lower() not in existing:
        raise RuntimeError(f'Cannot rebuild {table} because it does not exist.')
    if temp.lower() in existing:
        raise RuntimeError(f'Temporary table {temp} already exists. Remove it first.')

    if select is None:
        select = f'SELECT * FROM {_quote_identifier(table)}'

    # Remember the indexes and triggers, because DROP TABLE is about to delete
    # them. Automatic indexes from UNIQUE / PRIMARY KEY constraints have NULL
    # sql and come back on their own with the new table.
    query = '''
    SELECT sql FROM sqlite_master
    WHERE tbl_name == ? COLLATE NOCASE
    AND type IN ('index', 'trigger')
    AND sql IS NOT NULL
    ORDER BY type == 'trigger', rowid
    '''
    indices_triggers = execute(query, [table]).fetchall()

    execute(_rename_create_table(create, temp))
    execute(f'INSERT INTO {_quote_identifier(temp)} {select}')
    execute(f'DROP TABLE {_quote_identifier(table)}')
    execute(f'ALTER TABLE {_quote_identifier(temp)} RENAME TO {_quote_identifier(table)}')

    for (sql,) in indices_triggers:
        execute(sql)

def split_statements(script):
    script = _remove_script_comments(script)
    statements = []
    start_index = 0
    for semicolon in re.finditer(';', script):
        statement = script[start_index:semicolon.end()]
        if sqlite3.complete_statement(statement):
            statements.append(statement.strip())
            start_index = semicolon.end()

    remainder = script[start_index:]
    if remainder:
        statements.append(remainder)

    return statements

def upgrader(from_version, to_version):
    '''
    Decorate a database upgrade function so that it runs as a single
    transaction that moves the database from from_version to to_version, as
    recorded in PRAGMA user_version.

    The decorated function is called with the connection as its first argument,
    followed by whatever other arguments you pass, such as the path to the
    application's data directory. Inside the function, use rebuild_table and
    any other SQL you need. Don't commit or roll back yourself.

    The decorator:
    1. Remembers whether foreign keys are on, and turns them off. This must
       happen before the transaction, because SQLite silently ignores
       PRAGMA foreign_keys inside a transaction.
    2. BEGIN IMMEDIATE.
    3. Checks that PRAGMA user_version is from_version.
    4. Calls your function.
    5. Runs PRAGMA foreign_key_check.
    6. Sets PRAGMA user_version to to_version, and checks it.
    7. COMMIT.
    8. Turns foreign keys back on, if they were on before.
    If anything raises, the transaction is rolled back and foreign keys are
    restored, then the exception propagates.

    Upgrade functions should not use your application's code, such as its ORM
    or helper methods. The upgrade will be run by the latest version of your
    application, whose behavior may be different from when the upgrade was
    written. Stick to SQL and local file manipulation, and copy any logic you
    need into the upgrade function.

    The connection must not be in a transaction when the function is called.
    Connect with isolation_level=None, or with the default isolation_level,
    but not with autocommit=False on Python 3.12+, which keeps a transaction
    open at all times.

    The decorated function has attributes from_version and to_version, so you
    can collect your upgraders and run the ones you need with upgrade_all.
    '''
    for version in (from_version, to_version):
        if not isinstance(version, int) or isinstance(version, bool):
            raise TypeError(f'Versions must be int, not {type(version)}.')
    if to_version <= from_version:
        raise ValueError(f'to_version {to_version} must be greater than from_version {from_version}.')

    def decorator(upgrader_function):
        @functools.wraps(upgrader_function)
        def wrapped(connection, *args, **kwargs):
            foreign_keys = connection.execute('PRAGMA foreign_keys').fetchone()[0]
            connection.execute('PRAGMA foreign_keys = OFF')
            try:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    assert_user_version(connection, from_version)

                    log.info('Upgrading database from version %d to %d.', from_version, to_version)
                    upgrader_function(connection)

                    foreign_key_check(connection)

                    connection.execute(f'PRAGMA user_version = {to_version}')
                    new_version = connection.execute('PRAGMA user_version').fetchone()[0]
                    if new_version != to_version:
                        raise RuntimeError(f'Failed to set user_version to {to_version}, got {new_version}.')

                    connection.execute('COMMIT')
                except BaseException:
                    if connection.in_transaction:
                        connection.execute('ROLLBACK')
                    raise
            finally:
                if foreign_keys:
                    connection.execute('PRAGMA foreign_keys = ON')

            log.info('Upgraded database to version %d.', to_version)

        wrapped.from_version = from_version
        wrapped.to_version = to_version
        return wrapped
    return decorator
