'''
Worms is an SQL ORM with the strength and resilience of the humble earthworm.
'''
import abc
import functools
import random
import re
import sqlite3
import threading
import typing

from voussoirkit import pathclass
from voussoirkit import sqlhelpers
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'worms')

RNG = random.SystemRandom()

class WormException(Exception):
    pass

class BadTable(WormException):
    pass

class NoTransaction(WormException):
    pass

class TransactionActive(WormException):
    pass

class DeletedObject(WormException):
    '''
    For when thing.deleted == True.
    '''
    pass

# snake-cased because I want the ergonomics of a function from the caller's end.
class raise_without_rollback:
    def __init__(self, exc):
        self.exc = exc

def slice_before(li, item):
    index = li.index(item)
    return li[:index]

def atomic(method):
    '''
    This decorator can be added to functions that modify your worms database.
    A savepoint is opened, then your function is run. If an exception is raised,
    we roll back to the savepoint.

    This decorator adds the attribute 'is_worms_atomic = True' to your
    function. You can use this to distinguish readonly vs writing methods during
    runtime.

    If you want to raise an exception without rolling back, you can return
    worms.raise_without_rollback(exc). This could be useful if you want to
    preserve some kind of attempted action in the database while still raising
    the action's failure.
    '''
    @functools.wraps(method)
    def wrapped_atomic(self, *args, **kwargs):
        if isinstance(self, Object):
            self.assert_not_deleted()

        database = self._worms_database

        is_root = len(database.savepoints) == 0
        savepoint_id = database.savepoint(message=method.__qualname__)
        log.loud(f'{method.__qualname__} got savepoint {savepoint_id}.')

        try:
            result = method(self, *args, **kwargs)
        except BaseException as exc:
            log.debug(f'{method} raised {repr(exc)}.')
            database.rollback(savepoint=savepoint_id)
            raise

        if isinstance(result, raise_without_rollback):
            raise result.exc from result.exc

        if not is_root:
            # In order to prevent a huge pile-up of savepoints when a
            # @transaction calls another @transaction many times, the sub-call
            # savepoints are removed from the stack. When an exception occurs,
            # we're going to rollback from the rootmost savepoint anyway, we'll
            # never rollback one sub-transaction.
            database.release_savepoint(savepoint=savepoint_id)

        return result

    wrapped_atomic.is_worms_atomic = True
    return wrapped_atomic

class TransactionContextManager:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        log.loud('Entering transaction.')
        self.database.begin()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        log.loud('Exiting transaction.')
        if exc_type is not None:
            log.loud(f'Transaction raised {exc_type}.')
            self.database.rollback()
            raise exc_value

        self.database.commit()

class Database(metaclass=abc.ABCMeta):
    '''
    When your class subclasses this class, you need to ensure the following:
    - self.COLUMNS is a dictionary of {table: [columns]} like what comes out of
      sqlhelpers.extract_table_column_map.
    - self.COLUMN_INDEX is a dictionary of {table: {column: index}} like what
      comes out of sqlhelpers.reverse_table_column_map.
    '''
    def __init__(self):
        super().__init__()
        # Used for @atomic decorator
        self._worms_database = self
        self.on_commit_queue = []
        self.on_rollback_queue = []
        self.savepoints = []
        # To prevent two transactions from running at the same time in different
        # threads, and committing the database in an odd state, we lock out and
        # run one transaction at a time.
        self._worms_transaction_lock = threading.Lock()
        self._worms_transaction_owner = None
        self.transaction = TransactionContextManager(database=self)
        # Since user input usually comes in the form of strings -- from command
        # line, http requests -- and the IDs are usually ints in the database,
        # we'll do the data conversion before making queries or responses,
        # so you don't have to do it in your application.
        # But if your application uses string IDs, set self.id_type = str
        self.id_type = int
        self.last_commit_id = None

    @abc.abstractmethod
    def _init_column_index(self):
        '''
        Your subclass needs to set self.COLUMNS and self.COLUMN_INDEX, where
        COLUMNS is a dictionary of {'table': ['column1', 'column2', ...]} and
        COLUMN_INDEX is a dict of {'table': {'column1': 0, 'column2': 1}}.

        These outputs can come from sqlhelpers.extract_table_column_map and
        reverse_table_column_map.
        '''
        raise NotImplementedError

    @abc.abstractmethod
    def _init_sql(self):
        '''
        Your subclass needs to prepare self.sql_read and self.sql_write, which
        are both connection objects. They can be the same object if you want, or
        they can be separate connections so that the readers can not get blocked
        by the writers.

        You can do it yourself or use the provided _init_connections to get the
        basic handles going. Then use the rest of this method to do any other
        setup your application needs.
        '''
        raise NotImplementedError

    def _make_sqlite_read_connection(self, path):
        '''
        Provided for convenience of _init_sql.
        '''
        if isinstance(path, pathclass.Path):
            path = path.absolute_path
        if path == ':memory:':
            sql_read = sqlite3.connect('file:memdb1?mode=memory&cache=shared&mode=ro', uri=True)
            sql_read.row_factory = sqlite3.Row
        else:
            log.debug('Connecting to sqlite file "%s".', path)
            sql_read = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            sql_read.row_factory = sqlite3.Row
        return sql_read

    def _make_sqlite_write_connection(self, path):
        if isinstance(path, pathclass.Path):
            path = path.absolute_path

        if path == ':memory:':
            sql_write = sqlite3.connect('file:memdb1?mode=memory&cache=shared', uri=True)
            sql_write.row_factory = sqlite3.Row
        else:
            log.debug('Connecting to sqlite file "%s".', path)
            sql_write = sqlite3.connect(path)
            sql_write.row_factory = sqlite3.Row
        return sql_write

    def assert_no_transaction(self) -> None:
        thread_id = threading.current_thread().ident
        if self._worms_transaction_owner == thread_id:
            raise TransactionActive()

    def assert_transaction_active(self) -> None:
        thread_id = threading.current_thread().ident
        if self._worms_transaction_owner != thread_id:
            raise NoTransaction()

    def acquire_transaction_lock(self):
        '''
        If no transaction is running, the caller gets the lock.

        If a transaction is running on the same thread as the caller, the caller
        does not get the lock but the function returns so it can do its work,
        since it is a descendant of the original transaction call.

        If a transaction is running and the caller is on a different thread, it
        gets blocked until the previous transaction finishes.
        '''
        # Don't worry about race conditions, ownership of lock changing while
        # the if statement is evaluating, because this individual thread cannot
        # be checking its identity and releasing the lock at the same time! If
        # transaction_owner is the current thread, we know that will remain
        # true until this thread releases it, which can't happen at the same
        # time here.
        thread_id = threading.current_thread().ident
        if self._worms_transaction_owner == thread_id:
            return False

        log.loud(f'{thread_id} wants the transaction lock.')
        self._worms_transaction_lock.acquire()
        log.loud(f'{thread_id} has the transaction lock.')
        self._worms_transaction_owner = thread_id
        return True

    def assert_table_exists(self, table) -> None:
        if table not in self.COLUMN_INDEX:
            raise BadTable(f'Table {table} does not exist.')

    def begin(self):
        self.acquire_transaction_lock()
        self.execute('BEGIN')

    def close(self):
        # Wrapped in hasattr because if the object fails __init__, Python will
        # still call __del__ and thus close(), even though the attributes
        # we're trying to clean up never got set.
        if not hasattr(self, 'sql_read'):
            return

        if self._worms_transaction_owner:
            self.rollback()

        log.loud('Closing sql_read.')
        self.sql_read.close()
        del self.sql_read

        log.loud('Closing sql_write.')
        self.sql_write.close()
        del self.sql_write

    def commit(self, message=None) -> None:
        if message is None:
            log.debug('Committing.')
        else:
            log.debug('Committing - %s.', message)

        while len(self.on_commit_queue) > 0:
            task = self.on_commit_queue.pop(-1)
            if isinstance(task, int):
                # savepoints.
                continue
            args = task.get('args', [])
            kwargs = task.get('kwargs', {})
            action = task['action']
            log.loud(f'{action} {args} {kwargs}')
            try:
                action(*args, **kwargs)
            except Exception as exc:
                log.debug(f'{action} raised {repr(exc)}.')
                self.rollback()
                raise

        self.savepoints.clear()
        self.sql_write.commit()
        self.last_commit_id = RNG.getrandbits(32)
        self.release_transaction_lock()

    def delete(self, table, pairs) -> sqlite3.Cursor:
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.delete_filler(pairs)
        query = f'DELETE FROM {table} {qmarks}'
        return self.execute(query, bindings)

    def execute_read(self, query, bindings=[]):
        if bindings is None:
            bindings = []

        thread_id = threading.current_thread().ident
        if self._worms_transaction_owner == thread_id:
            sql = self.sql_write
        else:
            sql = self.sql_read

        cur = sql.cursor()
        log.loud('%s %s', query, bindings)
        cur.execute(query, bindings)
        return cur

    def execute(self, query, bindings=[]):
        self.assert_transaction_active()
        if bindings is None:
            bindings = []
        cur = self.sql_write.cursor()
        log.loud('%s %s', query, bindings)
        cur.execute(query, bindings)
        return cur

    def executescript(self, script) -> None:
        '''
        The problem with Python's default executescript is that it executes a
        COMMIT before running your script. If I wanted a commit I'd write one!
        '''
        self.assert_transaction_active()
        lines = re.split(r';(:?\n|$)', script)
        lines = (line.strip() for line in lines)
        lines = (line for line in lines if line)
        cur = self.sql_write.cursor()
        for line in lines:
            log.loud(line)
            cur.execute(line)

    def exists(self, query, bindings=None) -> bool:
        '''
        query should be a SELECT query.

        Returns True if at least one row was found, False if no rows found.
        '''
        row = self.select_one(query, bindings)
        return (row is not None)

    def explain(self, query, bindings=None) -> str:
        exp = self.execute_read('EXPLAIN QUERY PLAN ' + query, bindings)
        return '\n'.join(str(tuple(x)) for x in exp.fetchall())

    def get_object_by_id(self, object_class, object_id):
        '''
        Select an object by its ID.
        '''
        if isinstance(object_id, object_class):
            object_id = object_id.id

        object_id = self.normalize_object_id(object_class, object_id)
        query = f'SELECT * FROM {object_class.table} WHERE id == ?'
        bindings = [object_id]
        object_row = self.select_one(query, bindings)
        if object_row is None:
            raise object_class.no_such_exception(object_id)

        instance = object_class(self, object_row)

        return instance

    def get_objects(self, object_class):
        '''
        Yield objects, unfiltered, in whatever order they appear in the database.
        '''
        table = object_class.table
        query = f'SELECT * FROM {table}'

        objects = self.select(query)
        for object_row in objects:
            instance = object_class(self, object_row)
            yield instance

    def get_objects_by_id(self, object_class, object_ids, *, raise_for_missing=False):
        '''
        Select many objects by their IDs.

        This is better than calling get_object_by_id in a loop because we can
        use a single SQL select to get batches of up to 999 items.

        Note: The order of the output will most likely not match the order of
        the input. Consider using get_objects_by_sql if that is a necessity.

        raise_for_missing:
            If any of the requested object ids are not found in the database,
            we can raise that class's no_such_exception with the set of missing
            IDs.
        '''
        (object_ids, missing) = self.normalize_object_ids(object_ids)
        ids_needed = list(object_ids)
        ids_found = set()

        while ids_needed:
            # SQLite3 has a limit of 999 ? in a query, so we must batch them.
            id_batch = ids_needed[:999]
            ids_needed = ids_needed[999:]

            qmarks = ','.join('?' * len(id_batch))
            qmarks = f'({qmarks})'
            query = f'SELECT * FROM {object_class.table} WHERE id IN {qmarks}'
            for object_row in self.select(query, id_batch):
                instance = object_class(self, db_row=object_row)
                ids_found.add(instance.id)
                yield instance

        if raise_for_missing:
            missing.update(object_ids.difference(ids_found))
            if missing:
                raise object_class.no_such_exception(missing)

    def get_objects_by_sql(self, object_class, query, bindings=None):
        '''
        Use an arbitrary SQL query to select objects from the database.
        Your query should select * from the object's table.
        '''
        object_rows = self.select(query, bindings)
        for object_row in object_rows:
            yield object_class(self, object_row)

    def get_tables(self) -> set[str]:
        '''
        Return the set of all table names in the database.
        '''
        query = 'SELECT name FROM sqlite_master WHERE type = "table"'
        tables = set(self.select_column(query))
        return tables

    def insert(self, table, pairs) -> sqlite3.Cursor:
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.insert_filler(pairs)
        query = f'INSERT INTO {table} {qmarks}'
        return self.execute(query, bindings)

    def normalize_object_id(self, object_class, object_id):
        '''
        Given an object ID as input by the user, try to convert it using
        self.id_type. If that raises a ValueError, then we raise
        that class's no_such_exception.

        Just because an ID passes the type conversion does not mean that ID
        actually exists. We can raise the no_such_exception because an invalid
        ID certainly doesn't exist, but a valid one still might not exist.
        '''
        try:
            return self.id_type(object_id)
        except ValueError:
            raise object_class.no_such_exception(object_id)

    def normalize_object_ids(self, object_ids):
        '''
        Given a list of object ids, return two sets: the first set contains all
        the IDs that were able to be normalized using self.id_type; the second
        contains all the IDs that raised ValueError. This method does not raise
        the no_such_exception. as you may prefer to process the good instead of
        losing it all with an exception.

        Just because an ID passes the type conversion does not mean that ID
        actually exists.
        '''
        good = set()
        bad = set()
        for object_id in object_ids:
            try:
                good.add(self.id_type(object_id))
            except ValueError:
                bad.add(object_id)

        return (good, bad)

    def pragma_read(self, key):
        pragma = self.execute_read(f'PRAGMA {key}').fetchone()
        if pragma is not None:
            return pragma[0]
        return None

    def pragma_write(self, key, value) -> None:
        # We are bypassing self.execute because some pragmas are not allowed to
        # happen during transactions.
        return self.sql_write.cursor().execute(f'PRAGMA {key} = {value}')

    def release_savepoint(self, savepoint, allow_commit=False) -> None:
        '''
        Releasing a savepoint removes that savepoint from the timeline, so that
        you can no longer roll back to it. Then your choices are to commit
        everything, or roll back to a previous point. If you release the
        earliest savepoint, the database will commit.
        '''
        if savepoint not in self.savepoints:
            log.warn('Tried to release nonexistent savepoint %s.', savepoint)
            return

        is_commit = savepoint == self.savepoints[0]
        if is_commit and not allow_commit:
            log.debug('Not committing %s without allow_commit=True.', savepoint)
            return

        if is_commit:
            # We want to perform the on_commit_queue so let's use our commit
            # method instead of allowing sql's release to commit.
            self.commit()
        else:
            self.execute(f'RELEASE "{savepoint}"')
            self.savepoints = slice_before(self.savepoints, savepoint)

    def release_transaction_lock(self):
        thread_id = threading.current_thread().ident
        if not self._worms_transaction_lock.locked():
            return

        if self._worms_transaction_owner != thread_id:
            log.warning(f'{thread_id} tried to release the transaction lock without holding it.')
            return

        log.loud(f'{thread_id} releases the transaction lock.')
        self._worms_transaction_owner = None
        self._worms_transaction_lock.release()

    def rollback(self, savepoint=None) -> None:
        '''
        Given a savepoint, roll the database back to the moment before that
        savepoint was created. Keep in mind that a @transaction savepoint is
        always created *before* the method actually does anything.

        If no savepoint is provided then rollback the entire transaction.
        '''
        if savepoint is not None and savepoint not in self.savepoints:
            log.warn('Tried to restore nonexistent savepoint %s.', savepoint)
            return

        while len(self.on_rollback_queue) > 0:
            task = self.on_rollback_queue.pop(-1)
            if task == savepoint:
                break
            if isinstance(task, int):
                # Intermediate savepoints.
                continue
            args = task.get('args', [])
            kwargs = task.get('kwargs', {})
            task['action'](*args, **kwargs)

        if savepoint is not None:
            log.debug('Rolling back to %s.', savepoint)
            self.execute(f'ROLLBACK TO "{savepoint}"')
            self.savepoints = slice_before(self.savepoints, savepoint)
            self.on_commit_queue = slice_before(self.on_commit_queue, savepoint)

        else:
            log.debug('Rolling back.')
            self.execute('ROLLBACK')
            self.savepoints.clear()
            self.on_commit_queue.clear()
            self.release_transaction_lock()

    def savepoint(self, message=None) -> int:
        savepoint_id = RNG.getrandbits(32)
        if message:
            log.log(5, 'Savepoint %s for %s.', savepoint_id, message)
        else:
            log.log(5, 'Savepoint %s.', savepoint_id)
        query = f'SAVEPOINT "{savepoint_id}"'
        self.execute(query)
        self.savepoints.append(savepoint_id)
        self.on_commit_queue.append(savepoint_id)
        self.on_rollback_queue.append(savepoint_id)
        return savepoint_id

    def select(self, query, bindings=None) -> typing.Iterable:
        cur = self.execute_read(query, bindings)
        while True:
            fetch = cur.fetchone()
            if fetch is None:
                break
            yield fetch

    def select_column(self, query, bindings=None) -> typing.Iterable:
        '''
        If your SELECT query only selects a single column, you can use this
        function to get a generator of the individual values instead
        of one-tuples.
        '''
        for row in self.select(query, bindings):
            yield row[0]

    def select_one(self, query, bindings=None):
        '''
        Select a single row, or None if no rows match your query.
        '''
        cur = self.execute_read(query, bindings)
        return cur.fetchone()

    def select_one_value(self, query, bindings=None, fallback=None):
        '''
        Select a single column out of a single row, or fallback if no rows match
        your query. The fallback can help you distinguish between rows that
        don't exist and a null value.
        '''
        cur = self.execute_read(query, bindings)
        row = cur.fetchone()
        if row:
            return row[0]
        else:
            return fallback

    def update(self, table, pairs, where_key) -> sqlite3.Cursor:
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.update_filler(pairs, where_key=where_key)
        query = f'UPDATE {table} {qmarks}'
        return self.execute(query, bindings)

class DatabaseWithCaching(Database, metaclass=abc.ABCMeta):
    def __init__(self):
        super().__init__()
        self.caches = {}

    def _init_caches(self):
        '''
        Your subclass needs to set self.caches, which is a dictionary of
        {object: cache} where object is one of your data object types
        (use the class itself as the key) and cache is a dictionary or
        cacheclass.Cache or anything that supports subscripting.

        If any types are omitted from this dictionary, objects of those
        types will not be cached.
        '''
        raise NotImplementedError

    def clear_all_caches(self) -> None:
        for cache in self.caches:
            cache.clear()

    def get_cached_instance(self, object_class, db_row):
        '''
        Check if there is already an instance in the cache and return that.
        Otherwise, a new instance is created, cached, and returned.

        Note that in order to call this method you have to already have a
        db_row which means performing some select. If you only have the ID,
        use get_object_by_id, as there may already be a cached instance to save
        you the select.
        '''
        object_table = object_class.table
        object_cache = self.caches.get(object_class, None)

        if isinstance(db_row, (dict, sqlite3.Row)):
            object_id = db_row['id']
        else:
            object_index = self.COLUMN_INDEX[object_table]
            object_id = db_row[object_index['id']]

        if object_cache is None:
            return object_class(self, db_row)

        try:
            instance = object_cache[object_id]
        except KeyError:
            log.loud('Cache miss %s %s.', object_class, object_id)
            instance = object_class(self, db_row)
            object_cache[object_id] = instance
        return instance

    def get_object_by_id(self, object_class, object_id):
        '''
        This method will first check the cache to see if there is already an
        instance with that ID, in which case we don't need to perform any SQL
        select. If it is not in the cache, then a new instance is created,
        cached, and returned.
        '''
        if isinstance(object_id, object_class):
            # This could be used to check if your old reference to an object is
            # still in the cache, or re-select it from the db to make sure it
            # still exists and re-cache.
            # Probably an uncommon need but... no harm I think.
            object_id = object_id.id

        object_id = self.normalize_object_id(object_class, object_id)
        object_cache = self.caches.get(object_class, None)

        if object_cache is not None:
            try:
                return object_cache[object_id]
            except KeyError:
                pass

        query = f'SELECT * FROM {object_class.table} WHERE id == ?'
        bindings = [object_id]
        object_row = self.select_one(query, bindings)
        if object_row is None:
            raise object_class.no_such_exception(object_id)

        # Normally we would call `get_cached_instance` instead of
        # constructing here. But we already know for a fact that this
        # object is not in the cache.
        instance = object_class(self, object_row)

        if object_cache is not None:
            object_cache[instance.id] = instance

        return instance

    def get_objects(self, object_class):
        '''
        Yield objects, unfiltered, in whatever order they appear in the database.
        '''
        table = object_class.table
        query = f'SELECT * FROM {table}'

        objects = self.select(query)
        for object_row in objects:
            instance = self.get_cached_instance(object_class, object_row)
            yield instance

    def get_objects_by_id(self, object_class, object_ids, *, raise_for_missing=False):
        '''
        Given multiple IDs, this method will find which ones are in the cache
        and which ones need to be selected from the db.

        This is better than calling get_object_by_id in a loop because we can
        use a single SQL select to get batches of up to 999 items.

        Note: The order of the output will most likely not match the order of
        the input, because we first pull items from the cache before requesting
        the rest from the database.

        raise_for_missing:
            If any of the requested object ids are not found in the database,
            we can raise that class's no_such_exception with the set of missing
            IDs.
        '''
        object_cache = self.caches.get(object_class, None)

        (object_ids, missing) = self.normalize_object_ids(object_ids)
        ids_needed = set()
        ids_found = set()

        if object_cache is None:
            ids_needed.update(object_ids)
        else:
            for object_id in object_ids:
                try:
                    instance = object_cache[object_id]
                except KeyError:
                    ids_needed.add(object_id)
                else:
                    ids_found.add(object_id)
                    yield instance

        if not ids_needed:
            return

        if object_cache is not None:
            log.loud('Cache miss %s %s.', object_class.table, ids_needed)

        ids_needed = list(ids_needed)
        while ids_needed:
            # SQLite3 has a limit of 999 ? in a query, so we must batch them.
            id_batch = ids_needed[:999]
            ids_needed = ids_needed[999:]

            qmarks = ','.join('?' * len(id_batch))
            qmarks = f'({qmarks})'
            query = f'SELECT * FROM {object_class.table} WHERE id IN {qmarks}'
            for object_row in self.select(query, id_batch):
                # Normally we would call `get_cached_instance` instead of
                # constructing here. But we already know for a fact that this
                # object is not in the cache because it made it past the
                # previous loop.
                instance = object_class(self, db_row=object_row)
                if object_cache is not None:
                    object_cache[instance.id] = instance
                ids_found.add(instance.id)
                yield instance

        if raise_for_missing:
            missing.update(object_ids.difference(ids_found))
            if missing:
                raise object_class.no_such_exception(missing)

    def get_objects_by_sql(self, object_class, query, bindings=None):
        '''
        Use an arbitrary SQL query to select objects from the database.
        Your query should select * from the object's table.
        '''
        object_rows = self.select(query, bindings)
        for object_row in object_rows:
            yield self.get_cached_instance(object_class, object_row)

class Object(metaclass=abc.ABCMeta):
    '''
    When your objects subclass this class, you need to ensure the following:

    - self.table should be a string.
    - self.no_such_exception should be an exception class, to be raised when
      the user requests an instance of this class that does not exist.
      Initialized with a single argument, the requested ID.
    '''
    def __init__(self, database):
        '''
        Your subclass should call super().__init__(database).
        '''
        # Used for transaction
        self._worms_database = database
        self.deleted = False

    def __reinit__(self):
        '''
        Reload the row from the database and do __init__ with it.
        '''
        query = f'SELECT * FROM {self.table} WHERE id == ?'
        bindings = [self.id]
        row = self._worms_database.select_one(query, bindings)
        if row is None:
            self.deleted = True
        else:
            self.__init__(self._worms_database, row)

    def __eq__(self, other):
        return (
            isinstance(other, type(self)) and
            self._worms_database == other._worms_database and
            self.id == other.id
        )

    def __format__(self, formcode):
        if formcode == 'r':
            return repr(self)
        else:
            return str(self)

    def __hash__(self):
        return hash(f'{self.table}.{self.id}')

    def assert_not_deleted(self) -> None:
        '''
        Raises DeletedObject if this object is deleted.

        You need to set self.deleted during any method that deletes the object
        from the database.
        '''
        if self.deleted:
            raise DeletedObject(self)
