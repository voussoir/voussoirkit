'''
Worms is an SQL ORM with the strength and resilience of the humble earthworm.
'''
import abc
import functools
import random
import re
import typing

from voussoirkit import sqlhelpers
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'worms')

RNG = random.SystemRandom()

class WormException(Exception):
    pass

class BadTable(WormException):
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

def transaction(method):
    '''
    This decorator can be added to functions that modify your worms database.
    A savepoint is opened, then your function is run, then we roll back to the
    savepoint if an exception is raised.

    This decorator adds the keyword argument 'commit' to your function, so that
    callers can commit it immediately.

    If you want to raise an exception without rolling back, you can return
    worms.raise_without_rollback(exc). This could be useful if you want to
    preserve some kind of attempted action in the database while still raising
    the action's failure.
    '''
    @functools.wraps(method)
    def wrapped_transaction(self, *args, commit=False, **kwargs):
        if isinstance(self, Object):
            self.assert_not_deleted()

        database = self._worms_database

        is_root = len(database.savepoints) == 0
        savepoint_id = database.savepoint(message=method.__qualname__)

        try:
            result = method(self, *args, **kwargs)
        except BaseException as exc:
            log.debug(f'{method} raised {repr(exc)}.')
            database.rollback(savepoint=savepoint_id)
            raise

        if isinstance(result, raise_without_rollback):
            raise result.exc from result.exc

        if commit:
            database.commit(message=method.__qualname__)
        elif not is_root:
            # In order to prevent a huge pile-up of savepoints when a
            # @transaction calls another @transaction many times, the sub-call
            # savepoints are removed from the stack. When an exception occurs,
            # we're going to rollback from the rootmost savepoint anyway, we'll
            # never rollback one sub-transaction.
            database.release_savepoint(savepoint=savepoint_id)
        return result

    return wrapped_transaction

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
        # Used for transaction
        self._worms_database = self
        self.on_commit_queue = []
        self.on_rollback_queue = []
        self.savepoints = []
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
        Your subclass needs to set self.sql, which is a database connection.

        It is recommended to set self.sql.row_factory = sqlite3.Row so that you
        get dictionary-style named access to row members in your objects' init.
        '''
        raise NotImplementedError

    def assert_table_exists(self, table) -> None:
        if table not in self.COLUMN_INDEX:
            raise BadTable(f'Table {table} does not exist.')

    def close(self):
        # Wrapped in hasattr because if the object fails __init__, Python will
        # still call __del__ and thus close(), even though the attributes
        # we're trying to clean up never got set.
        if hasattr(self, 'sql'):
            self.sql.close()

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
            try:
                action(*args, **kwargs)
            except Exception as exc:
                log.debug(f'{action} raised {repr(exc)}.')
                self.rollback()
                raise

        self.savepoints.clear()
        self.sql.commit()
        self.last_commit_id = RNG.getrandbits(32)

    def delete(self, table, pairs) -> None:
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.delete_filler(pairs)
        query = f'DELETE FROM {table} {qmarks}'
        return self.execute(query, bindings)

    def execute(self, query, bindings=[]):
        if bindings is None:
            bindings = []
        cur = self.sql.cursor()
        log.loud('%s %s', query, bindings)
        cur.execute(query, bindings)
        return cur

    def executescript(self, script) -> None:
        '''
        The problem with Python's default executescript is that it executes a
        COMMIT before running your script. If I wanted a commit I'd write one!
        '''
        lines = re.split(r';(:?\n|$)', script)
        lines = (line.strip() for line in lines)
        lines = (line for line in lines if line)
        cur = self.sql.cursor()
        for line in lines:
            log.loud(line)
            cur.execute(line)

    def get_object_by_id(self, object_class, object_id):
        '''
        Select an object by its ID.
        '''
        if isinstance(object_id, object_class):
            object_id = object_id.id

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
        object_ids = set(object_ids)
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
            missing = object_ids.difference(ids_found)
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

    def insert(self, table, data) -> None:
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        self.assert_table_exists(table)
        column_names = self.COLUMNS[table]
        (qmarks, bindings) = sqlhelpers.insert_filler(column_names, data)

        query = f'INSERT INTO {table} VALUES({qmarks})'
        return self.execute(query, bindings)

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

        if len(self.savepoints) == 0:
            log.debug('Nothing to roll back.')
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

    def savepoint(self, message=None) -> str:
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
        cur = self.execute(query, bindings)
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
        cur = self.execute(query, bindings)
        return cur.fetchone()

    def select_one_value(self, query, bindings=None):
        '''
        Select a single column out of a single row, or None if no rows match
        your query.
        '''
        cur = self.execute(query, bindings)
        row = cur.fetchone()
        if row:
            return row[0]
        else:
            return None

    def update(self, table, pairs, where_key) -> None:
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

        if isinstance(db_row, dict):
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

        object_ids = set(object_ids)
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
            missing = object_ids.difference(ids_found)
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
