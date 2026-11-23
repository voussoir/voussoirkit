'''
Worms is an SQLite ORM with the strength and resilience of the humble earthworm.
'''
import abc
import contextlib
import functools
import pathlib
import queue
import random
import sqlite3
import threading
import typing

from voussoirkit import pathclass
from voussoirkit import sqlhelpers
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'worms')

RNG = random.SystemRandom()

DEFAULT_READ_POOL_SIZE = 5

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
            try:
                database.rollback(savepoint=savepoint_id)
            except BaseException as rollback_exc:
                log.error('Rollback to savepoint %s raised %r.', savepoint_id, rollback_exc)
            raise

        if isinstance(result, raise_without_rollback):
            raise result.exc from result.exc

        if not is_root:
            # In order to prevent a huge pile-up of savepoints when a
            # @atomic calls another @atomic many times, the sub-call
            # savepoints are removed from the stack. When an exception occurs,
            # we're going to rollback from the rootmost savepoint anyway, we'll
            # never rollback one sub-transaction.
            database.release_savepoint(savepoint=savepoint_id)

        return result

    wrapped_atomic.is_worms_atomic = True
    return wrapped_atomic

class ConnectionManager:
    '''
    Own the SQLite connections and the write lock.

    The write lock decides which thread may use the write connection. A
    transaction is one reason to hold it (see begin); a single statement that
    must not run inside a transaction, like some PRAGMAs, is another (see
    _write_lock_context).

    This class provides connections, cursors, and transaction bookkeeping.
    SQL query helpers and ORM methods belong to Database.
    '''
    def __init__(self, *, read_pool_size=DEFAULT_READ_POOL_SIZE):
        if not isinstance(read_pool_size, int) or read_pool_size < 1:
            raise ValueError('read_pool_size must be a positive integer.')

        self._read_pool_size = read_pool_size
        self._read_leases = {}
        self._write_lock = threading.Lock()
        self._write_owner = None
        self._all_connections = []
        self.savepoints = []
        self.on_commit_queue = []
        self.on_rollback_queue = []
        self.last_commit_id = None

    def _acquire_write_lock(self):
        '''
        Block until this thread holds the write lock.

        If this thread already holds it, we raise TransactionActive rather than
        deadlock. If this thread is leasing a read connection, we also raise
        TransactionActive, because its reads would stay on the read connection
        and not see its own writes.

        Called by begin and _write_lock_context. The lock is released by
        _release_write_lock, from commit, rollback, or _write_lock_context.
        '''
        # Don't worry about race conditions, ownership of lock changing while
        # the if statement is evaluating, because this individual thread cannot
        # be checking its identity and releasing the lock at the same time! If
        # write_owner is the current thread, we know that will remain true
        # until this thread releases it, which can't happen at the same time
        # here.
        thread = threading.current_thread()
        if self._write_owner is thread:
            raise TransactionActive()

        if thread in self._read_leases:
            raise TransactionActive('Cannot take the write lock while this thread is using a read connection, e.g. inside a select_generator loop.')

        log.loud(f'{thread.ident} wants the write lock.')
        self._write_lock.acquire()
        self._write_owner = thread
        log.loud(f'{thread.ident} has the write lock.')
        return True

    def _do_on_commit_queue(self):
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
            except BaseException as action_exc:
                log.debug(f'{action} raised {action_exc!r}.')
                raise

    def _do_on_rollback_queue(self, savepoint):
        action_error = None
        while len(self.on_rollback_queue) > 0:
            task = self.on_rollback_queue.pop(-1)
            if task == savepoint:
                break
            if isinstance(task, int):
                # Intermediate savepoints.
                continue
            args = task.get('args', [])
            kwargs = task.get('kwargs', {})
            try:
                task['action'](*args, **kwargs)
            except BaseException as exc:
                log.error('Rollback action %r raised %r.', task['action'], exc)
                if action_error is None:
                    action_error = exc
        return action_error

    def _make_connection(self, path, read_only=False):
        if isinstance(path, pathclass.Path):
            path = path.absolute_path

        if path == ':memory:':
            connection = sqlite3.connect(f'file:{self._memdb_random}?mode=memory&cache=shared', uri=True, check_same_thread=False)
            connection.row_factory = sqlite3.Row
        else:
            log.debug('Connecting to sqlite file "%s".', path)
            mode = '?mode=ro' if read_only else ''
            path_uri = pathlib.Path(path).absolute().as_uri()
            connection = sqlite3.connect(f'{path_uri}{mode}', uri=True, check_same_thread=False)
            connection.row_factory = sqlite3.Row

        if read_only:
            connection.execute('PRAGMA query_only = true')
            connection.execute('PRAGMA cache_size = 10000')
        else:
            connection.execute('PRAGMA foreign_keys = on')
            journal_mode = connection.execute('PRAGMA journal_mode = WAL').fetchone()[0]
            if journal_mode not in {'wal', 'memory'}:
                log.warning('Could not enable WAL, journal_mode is %s.', journal_mode)
            connection.execute('PRAGMA cache_size = 10000')
            # Read-only connections cannot create the -shm file themselves, so
            # we make the writer create it before the read pool connects.
            connection.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchall()

        return connection

    @contextlib.contextmanager
    def _read_connection_context(self):
        '''
        Lease a read connection.

        A thread inside a transaction uses the write connection so that it can
        see uncommitted changes. Other threads lease from the read pool.

        While a thread already has a connection, further reads on that thread
        reuse it. depth counts the read contexts using it, whether nested or
        interleaved (e.g. two select_generators iterated alternately), and the
        connection goes back to the pool only when depth returns to zero, no
        matter which context finishes last.

        Leases are keyed by thread in a plain dict rather than a threading.local
        because an abandoned select_generator may be garbage collected on a
        different thread. The cleanup must update the lease of the thread that
        started the read, not whichever thread happens to run the finalizer.
        '''
        thread = threading.current_thread()
        lease = self._read_leases.get(thread)
        if lease is None:
            from_pool = self._write_owner is not thread
            if from_pool:
                log.loud(f'Want a read connection, there are {self._read_connection_pool.qsize()} available.')
                connection = self._read_connection_pool.get()
            else:
                connection = self._write_connection
            lease = {'connection': connection, 'from_pool': from_pool, 'depth': 0}
            self._read_leases[thread] = lease

        lease['depth'] += 1
        try:
            yield lease['connection']
        finally:
            lease['depth'] -= 1
            if lease['depth'] == 0:
                del self._read_leases[thread]
                if lease['from_pool']:
                    self._read_connection_pool.put(lease['connection'])

    @contextlib.contextmanager
    def _read_cursor_context(self):
        '''
        Lease a read connection and a cursor on it.
        '''
        with self._read_connection_context() as connection:
            cur = connection.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def _release_write_lock(self):
        thread = threading.current_thread()
        if not self._write_lock.locked():
            return

        if self._write_owner is not thread:
            log.warning(f'{thread.ident} tried to release the write lock without holding it.')
            return

        log.loud(f'{thread.ident} releases the write lock.')
        self._write_owner = None
        self._write_lock.release()

    @contextlib.contextmanager
    def _write_cursor_context(self):
        '''
        Yield a cursor on the write connection.

        The caller must already hold the write lock. This method never acquires
        it, so that a write attempted outside of a transaction raises
        NoTransaction instead of silently autocommitting.
        '''
        self.assert_transaction_owner()
        cur = self._write_connection.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def _write_connection_in_transaction(self) -> bool:
        try:
            return self._write_connection.in_transaction
        except sqlite3.ProgrammingError:
            # Closing the connection already ended any transaction.
            return False
        except BaseException:
            # If the state cannot be determined, assume the transaction is
            # still active. Callers use this result to decide whether to
            # release the write lock, so returning False here could let
            # another thread use a connection that is still mid-transaction.
            return True

    @contextlib.contextmanager
    def _write_lock_context(self):
        '''
        Hold the write lock without starting a transaction, for statements
        like some PRAGMAs and VACUUM which cannot run inside one.

        If this thread already holds the write lock, e.g. because it is inside
        a transaction, this does nothing extra and your statement runs inside
        that transaction. Otherwise we wait for the lock, and release it after.

        Do not run INSERT / UPDATE / DELETE in here. Python's sqlite3 would
        implicitly BEGIN a transaction for them, and we'd roll it back on exit.
        '''
        if self._write_owner is threading.current_thread():
            yield
            return

        self._acquire_write_lock()
        try:
            yield
        finally:
            try:
                if self._write_connection_in_transaction():
                    log.error('A transaction was left open under the write lock, rolling back.')
                    self._write_connection.rollback()
            finally:
                self._release_write_lock()

    def assert_no_transaction(self) -> None:
        if self.has_transaction():
            raise TransactionActive()

    def assert_transaction_active(self) -> None:
        if not self.has_transaction():
            raise NoTransaction()

    def assert_transaction_owner(self) -> None:
        if self._write_owner is not threading.current_thread():
            raise NoTransaction()

    def begin(self, transaction_mode='IMMEDIATE') -> None:
        '''
        Acquire the write lock and start a SQL transaction.
        '''
        if transaction_mode not in {'DEFERRED', 'IMMEDIATE', 'EXCLUSIVE'}:
            raise ValueError(transaction_mode)

        self._acquire_write_lock()
        try:
            with self._write_cursor_context() as cur:
                cur.execute(f'BEGIN {transaction_mode}')
        except BaseException:
            self._release_write_lock()
            raise

    def close(self):
        if self._write_owner:
            if self._write_owner is not threading.current_thread():
                raise TransactionActive()
            else:
                self.rollback()

        log.loud('Closing all connections.')
        for connection in self._all_connections:
            connection.close()

        self._all_connections = []

    def commit(self, message=None) -> None:
        self.assert_transaction_owner()

        if message is None:
            log.debug('Committing.')
        else:
            log.debug('Committing - %s.', message)

        try:
            self._do_on_commit_queue()
            self._write_connection.commit()
        except BaseException as exc:
            log.debug(f'Commit failed: {exc!r}.')
            try:
                self.rollback()
            except BaseException as rollback_exc:
                log.error('Rollback after failed commit raised %r.', rollback_exc)
            raise

        self.savepoints.clear()
        self.on_rollback_queue.clear()
        self.last_commit_id = RNG.getrandbits(32)
        self._release_write_lock()

    def connect(self, path):
        self._memdb_random = RNG.getrandbits(32)
        self._all_connections = []
        self._write_connection = self._make_connection(path)
        self._all_connections.append(self._write_connection)
        self._read_connection_pool = queue.Queue(maxsize=self._read_pool_size)
        for x in range(self._read_pool_size):
            reader = self._make_connection(path, read_only=True)
            self._read_connection_pool.put(reader)
            self._all_connections.append(reader)

        # The write connection must be last so that it will be closed last,
        # which is important to clear the journal files.
        self._all_connections.reverse()

    def has_transaction(self):
        '''
        True if any thread is inside a transaction. A thread holding the write
        lock for a lone PRAGMA does not count.
        '''
        return self._write_owner is not None and self._write_connection_in_transaction()

    def release_savepoint(self, savepoint, allow_commit=False) -> None:
        '''
        Releasing a savepoint removes that savepoint from the timeline, so that
        you can no longer roll back to it. Then your choices are to commit
        everything, or roll back to a previous point. If you release the
        earliest savepoint, the database will commit.
        '''
        if savepoint not in self.savepoints:
            log.warning('Tried to release nonexistent savepoint %s.', savepoint)
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
            with self._write_cursor_context() as cur:
                cur.execute(f'RELEASE "{savepoint}"')
            self.savepoints = slice_before(self.savepoints, savepoint)

    def rollback(self, savepoint=None) -> None:
        '''
        Given a savepoint, roll the database back to the moment before that
        savepoint was created. Keep in mind that an @atomic savepoint is
        always created *before* the method actually does anything.

        If no savepoint is provided then rollback the entire transaction.
        '''
        self.assert_transaction_owner()

        if savepoint is not None and savepoint not in self.savepoints:
            log.warning('Tried to restore nonexistent savepoint %s.', savepoint)
            return

        if not self._write_connection_in_transaction():
            log.warning('Rollback called with no active transaction.')
            self.savepoints.clear()
            self.on_commit_queue.clear()
            self.on_rollback_queue.clear()
            self._release_write_lock()
            return

        action_error = self._do_on_rollback_queue(savepoint)

        if savepoint is not None:
            log.debug('Rolling back to %s.', savepoint)
            try:
                with self._write_cursor_context() as cur:
                    cur.execute(f'ROLLBACK TO "{savepoint}"')
            except BaseException:
                log.error('Rollback to savepoint %s failed.', savepoint)
                raise
            self.savepoints = slice_before(self.savepoints, savepoint)
            self.on_commit_queue = slice_before(self.on_commit_queue, savepoint)
            if action_error is not None:
                raise action_error
            return

        log.debug('Rolling back.')
        sql_error = None
        try:
            with self._write_cursor_context() as cur:
                cur.execute('ROLLBACK')
        except BaseException as exc:
            sql_error = exc
            failed_in_transaction = self._write_connection_in_transaction()
            if failed_in_transaction:
                log.error('Rollback failed: %r. Closing the write connection.', exc)
                try:
                    self._write_connection.close()
                except BaseException as close_exc:
                    log.error('Closing the write connection failed: %r.', close_exc)
            else:
                log.debug('Rollback failed, but the transaction has ended: %r.', exc)

        still_active = self._write_connection_in_transaction()
        if still_active:
            log.error('Write transaction is still active after rollback, holds write lock.')
        else:
            self.savepoints.clear()
            self.on_commit_queue.clear()
            self.on_rollback_queue.clear()
            self._release_write_lock()

        if sql_error is not None:
            raise sql_error

        if action_error is not None:
            raise action_error

    def savepoint(self, message=None) -> int:
        savepoint_id = RNG.getrandbits(32)
        if message:
            log.log(5, 'Savepoint %s for %s.', savepoint_id, message)
        else:
            log.log(5, 'Savepoint %s.', savepoint_id)
        with self._write_cursor_context() as cur:
            cur.execute(f'SAVEPOINT "{savepoint_id}"')
        self.savepoints.append(savepoint_id)
        self.on_commit_queue.append(savepoint_id)
        self.on_rollback_queue.append(savepoint_id)
        return savepoint_id

class Database:
    def __init__(self, read_pool_size=DEFAULT_READ_POOL_SIZE):
        super().__init__()
        self._connectionmanager = ConnectionManager(read_pool_size=read_pool_size)

        # Used for @atomic decorator
        self._worms_database = self

        # Since user input usually comes in the form of strings -- from command
        # line, http requests -- and the IDs are usually ints in the database,
        # we'll do the data conversion before making queries or responses,
        # so you don't have to do it in your application.
        # But if your application uses string IDs, set self.id_type = str
        self.id_type = int

    @property
    def last_commit_id(self):
        return self._connectionmanager.last_commit_id

    @property
    def on_commit_queue(self):
        return self._connectionmanager.on_commit_queue

    @property
    def on_rollback_queue(self):
        return self._connectionmanager.on_rollback_queue

    @property
    def savepoints(self):
        return self._connectionmanager.savepoints

    def assert_no_transaction(self) -> None:
        self._connectionmanager.assert_no_transaction()

    def assert_transaction_active(self) -> None:
        self._connectionmanager.assert_transaction_active()

    def assert_transaction_owner(self) -> None:
        self._connectionmanager.assert_transaction_owner()

    def close(self):
        self._connectionmanager.close()

    def commit(self, message=None) -> None:
        self._connectionmanager.commit(message=message)

    def connect(self, path):
        self._connectionmanager.connect(path)

    @property
    @contextlib.contextmanager
    def transaction(self):
        log.loud('Entering transaction.')
        self._connectionmanager.begin('IMMEDIATE')

        try:
            yield self
        except BaseException as exc:
            log.loud(f'Transaction raised {exc!r}.')
            try:
                self.rollback()
            except BaseException as rollback_exc:
                log.error('Rollback during transaction exit raised %r.', rollback_exc)
            raise
        else:
            log.loud('Exiting transaction.')
            if self._connectionmanager._write_owner is threading.current_thread():
                self.commit()
            else:
                log.debug('Someone else closed the transaction.')

    def release_savepoint(self, savepoint, allow_commit=False) -> None:
        self._connectionmanager.release_savepoint(savepoint=savepoint, allow_commit=allow_commit)

    def rollback(self, savepoint=None) -> None:
        self._connectionmanager.rollback(savepoint=savepoint)

    def savepoint(self, message=None) -> int:
        return self._connectionmanager.savepoint(message=message)

    # SQL CORE METHODS #############################################################################

    def execute_read_all(self, query, bindings=None) -> list:
        if bindings is None:
            bindings = []

        log.loud('%s %s', query, bindings)
        with self._connectionmanager._read_cursor_context() as cur:
            cur.execute(query, bindings)
            return cur.fetchall()

    def execute_read_one(self, query, bindings=None):
        if bindings is None:
            bindings = []

        log.loud('%s %s', query, bindings)
        with self._connectionmanager._read_cursor_context() as cur:
            cur.execute(query, bindings)
            return cur.fetchone()

    def execute_write(self, query, bindings=None):
        '''
        Your query will be executed over the write connection. You must have a
        transaction active before calling here or else NoTransaction is raised.
        '''
        if bindings is None:
            bindings = []
        log.loud('%s %s', query, bindings)
        with self._connectionmanager._write_cursor_context() as cur:
            cur.execute(query, bindings)
            return (cur.lastrowid, cur.rowcount)

    def execute_script(self, script) -> None:
        '''
        The problem with Python's default executescript is that it executes a
        COMMIT before running your script. If I wanted a commit I'd write one!

        Your script will be executed over the write connection. You must have a
        transaction active before calling here or else NoTransaction is raised.
        '''
        with self._connectionmanager._write_cursor_context() as cur:
            for statement in sqlhelpers.split_statements(script):
                cur.execute(statement)

    def select(self, query, bindings=None) -> list:
        return self.execute_read_all(query, bindings)

    def select_exists(self, query, bindings=None) -> bool:
        '''
        query should be a SELECT query, usually `SELECT 1 FROM table WHERE`.

        Returns True if at least one row was found, False if no rows found.
        '''
        row = self.select_one(query, bindings)
        return (row is not None)

    def select_column(self, query, bindings=None) -> typing.Iterable:
        '''
        If your SELECT query only selects a single column, you can use this
        function to get a generator of the individual values instead
        of one-tuples.
        '''
        for row in self.select(query, bindings):
            yield row[0]

    def select_generator(self, query, bindings=None) -> typing.Iterable:
        if self._connectionmanager._write_owner is threading.current_thread():
            raise TransactionActive('Cannot start a select_generator from an open transaction.')

        if bindings is None:
            bindings = []

        log.loud('%s %s', query, bindings)
        with self._connectionmanager._read_cursor_context() as cur:
            cur.execute(query, bindings)
            yield from cur

    def select_one(self, query, bindings=None, fallback=None):
        '''
        Select a single row, or fallback if no rows match your query.
        '''
        row = self.execute_read_one(query, bindings)
        if row is None:
            return fallback
        return row

    def select_one_value(self, query, bindings=None, fallback=None):
        '''
        Select a single column out of a single row, or fallback if no rows match
        your query. The fallback can help you distinguish between rows that
        don't exist and a null value.
        '''
        row = self.execute_read_one(query, bindings)
        if row is None:
            return fallback
        return row[0]

    def assert_table_exists(self, table) -> None:
        exists = self.select_exists("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table])
        if not exists:
            raise BadTable(f'Table {table} does not exist.')

    def backup(self, destination) -> None:
        '''
        Copy the database to the destination filepath using SQLite's online
        backup API. If the destination file already exists, its contents are
        replaced.

        The copy is taken from a read connection, so it is a consistent
        snapshot of the last commit and other threads can keep writing during
        the backup.

        Cannot be called from inside a transaction, because SQLite refuses to
        back up from a connection that is in the middle of writing.
        '''
        if self._connectionmanager._write_owner is threading.current_thread():
            raise TransactionActive('Cannot back up from an open transaction.')

        destination = pathclass.Path(destination).absolute_path

        log.debug('Backing up database to "%s".', destination)
        with self._connectionmanager._read_connection_context() as source:
            with contextlib.closing(sqlite3.connect(destination)) as dest:
                source.backup(dest)

    def explain(self, query, bindings=None) -> str:
        exp = self.select('EXPLAIN QUERY PLAN ' + query, bindings)
        return '\n'.join(str(tuple(x)) for x in exp)

    def get_tables(self) -> set[str]:
        '''
        Return the set of all table names in the database.
        '''
        query = "SELECT name FROM sqlite_master WHERE type = 'table'"
        tables = set(self.select_column(query))
        return tables

    def pragma_read_all(self, key) -> list:
        '''
        Execute a PRAGMA on the write connection and return all of its rows.

        PRAGMAs are always read from the write connection, not the read pool,
        because some PRAGMAs like foreign_keys and cache_size are per-connection
        settings, and pragma_write only sets them on the write connection. This
        way, pragma_read reports what pragma_write set.

        If this thread is inside a transaction, the PRAGMA is read inside it,
        so you will see your own uncommitted changes, e.g. to user_version.
        Otherwise, we wait for the write lock, so this will block while another
        thread has a transaction open.
        '''
        with self._connectionmanager._write_lock_context():
            with self._connectionmanager._write_cursor_context() as cur:
                cur.execute(f'PRAGMA {key}')
                return cur.fetchall()

    def pragma_read_one(self, key):
        '''
        Like pragma_read_all, but return only the first column of the first
        row, or None if the PRAGMA returned no rows.
        '''
        rows = self.pragma_read_all(key)
        if not rows:
            return None
        return rows[0][0]

    def pragma_write(self, key, value) -> list:
        '''
        Execute a PRAGMA on the write connection.

        If this thread is inside a transaction, the PRAGMA runs inside it. This
        is what you want for user_version during a migration, because it will
        commit or roll back along with your schema changes. Note that some
        PRAGMAs are not allowed in a transaction: journal_mode raises an error,
        and foreign_keys is silently ignored.

        Otherwise, we wait for the write lock, run the PRAGMA which takes effect
        immediately, and release the lock.

        Connection-level PRAGMAs like foreign_keys and cache_size only affect
        the write connection, not the read pool.

        The returned rows are the PRAGMA's result; journal_mode returns the
        resulting mode, so callers can verify it.
        '''
        with self._connectionmanager._write_lock_context():
            with self._connectionmanager._write_cursor_context() as cur:
                cur.execute(f'PRAGMA {key} = {value}')
                return cur.fetchall()

    # ORM METHODS ##################################################################################

    def delete(self, table, pairs):
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        # self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.delete_filler(pairs)
        query = f'DELETE FROM {table} {qmarks}'
        return self.execute_write(query, bindings)

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
                instance = object_class(self, object_row)
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

    def insert(self, table, pairs, *, ignore_duplicate=False):
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        # self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.insert_filler(pairs)
        if ignore_duplicate:
            query = f'INSERT OR IGNORE INTO {table} {qmarks}'
        else:
            query = f'INSERT INTO {table} {qmarks}'
        return self.execute_write(query, bindings)

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

    def update(self, table, pairs, where_key):
        if isinstance(table, type) and issubclass(table, Object):
            table = table.table
        # self.assert_table_exists(table)
        (qmarks, bindings) = sqlhelpers.update_filler(pairs, where_key=where_key)
        query = f'UPDATE {table} {qmarks}'
        return self.execute_write(query, bindings)

class DatabaseWithCaching(Database, metaclass=abc.ABCMeta):
    def __init__(self, read_pool_size=DEFAULT_READ_POOL_SIZE):
        super().__init__(read_pool_size=read_pool_size)
        self.caches = {}

    def _init_caches(self):
        '''
        Your subclass needs to set self.caches, which is a dictionary of
        {object: cache} where object is one of your data object types
        (use the class itself as the key) and cache is a dictionary or
        cacheclass.Cache or anything that supports subscripting and `.clear`.

        If any types are omitted from this dictionary, objects of those
        types will not be cached.
        '''
        raise NotImplementedError

    def clear_all_caches(self) -> None:
        for cache in self.caches.values():
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

        if object_cache is None:
            log.loud('The %s table is not cached. Returning new instance.', object_class.table)
            return object_class(self, db_row)

        object_id = db_row['id']

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
                instance = object_class(self, object_row)
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
        super().__init__()
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
