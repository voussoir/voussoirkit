import flask; from flask import request
import functools
import gzip
import io
import json
import queue
import random
import threading
import time
import werkzeug.wrappers

from voussoirkit import bytestring
from voussoirkit import cacheclass
from voussoirkit import dotdict
from voussoirkit import sentinel
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

RNG = random.SystemRandom()

GZIP_MINIMUM_SIZE = 500 * bytestring.BYTE
GZIP_MAXIMUM_SIZE = 5 * bytestring.MEBIBYTE
GZIP_LEVEL = 3

REQUEST_TYPES = (flask.Request, werkzeug.wrappers.Request, werkzeug.local.LocalProxy)
RESPONSE_TYPES = (flask.Response, werkzeug.wrappers.Response)

NOT_CACHED = sentinel.Sentinel('not cached', truthyness=False)

SSE_LISTENERS = set()
SSE_LISTENERS_LOCK = threading.Lock()

def cached_endpoint(max_age, etag_function=None, max_urls=1000):
    '''
    The cached_endpoint decorator can be used on slow endpoints that don't need
    to be constantly updated or endpoints that produce large, static responses.

    WARNING: The return value of the endpoint is shared with all users.
    You should never use this cache on an endpoint that provides private
    or personalized data, and you should not try to pass other headers through
    the response.

    When the function is run, its return value is stored and an etag is
    generated so that subsequent runs can respond with 304. This way, large
    response bodies do not need to be transmitted often.

    An example use case would be large-sized data dumps that don't need to be
    precisely up to date every time.

    max_age:
        Your endpoint function will only be called once per max_age seconds on
        a global basis (not per-user). This way, you can prevent a slow function
        from being run very often. In-between requests will just receive the
        previous return value (still using 200 or 304 as appropriate for the
        client's provided etag).

        max_age will also be added to the Cache-Control response header.

    etag_function:
        If None, this decorator will call your endpoint function and compare the
        return value with the stored return value to see if it has changed. If
        it has not changed, the user will get a 304 and save their bandwidth,
        however all of the computation done by your function to make that return
        value is otherwise wasted. If your function is very expensive to run,
        or if you want to use a small max_age, you might want to provide a
        dedicated etag_function that takes into account more of the world state.

        This function will be called before your endpoint function is called.
        If the etag_function return value doesn't change, we assume the endpoint
        function's value would not change either, and we return the 304, saving
        both bandwidth and computation. This allows a cheap etag_function such
        as "when was the last db commit" to save you from a more expensive
        function call like "generate a json dump of database objects", since the
        json output probably hasn't changed if there hasn't been a more recent
        commit.

        The function should take no arguments.

        The max_age check comes before the etag_function check, so even the
        etag_function won't be run if we're still within the age limit.

    max_urls:
        Every permutation of request path params dict will have a separate
        cached value. You can control how many URLs will be kept in the
        least-recently used cache.
    '''
    if max_age < 0:
        raise ValueError(f'max_age should be positive, not {max_age}.')

    def new_state():
        # The server_etag is kept separate from the client_etag so that there's
        # no possibility of leaking anything important to the user from your
        # etag_function. They will always get a random string.
        state = dotdict.DotDict({
            'max_age': max_age,
            'stored_value': NOT_CACHED,
            'client_etag': None,
            'server_etag': None,
            'headers': {'ETag': None, 'Cache-Control': f'max-age={max_age}'},
            'last_run': 0,
        })
        return state

    states = cacheclass.Cache(maxlen=max_urls)

    def wrapper(function):
        def can_reuse_state(state):
            # This function does not necessarily indicate that the user will
            # get a 304 as we are not checking their etag yet. After all, we
            # shouldn't check their etag until we know whether the internal
            # state is fresh enough to check against.

            if state.stored_value is NOT_CACHED:
                return False

            if (time.monotonic() - state.last_run) < state.max_age:
                return True

            if etag_function is None:
                return False

            if state.server_etag == etag_function():
                # log.debug('Reusing server etag %s.', state.server_etag)
                return True

        def update_state(state, *args, **kwargs):
            value = function(*args, **kwargs)
            if isinstance(value, flask.Response):
                if value.headers.get('Content-Type'):
                    state.headers['Content-Type'] = value.headers.get('Content-Type')
                value = value.response

            # It's possible that both the max_age and etag_function have
            # indicated the data is stale, but actually it's the same.
            if value != state.stored_value:
                state.stored_value = value
                # The user's request header will come in as a string anyway.
                state.client_etag = str(RNG.getrandbits(32))
                state.headers['ETag'] = state.client_etag

            # I would have liked to reuse the value from the call made in
            # can_reuse_state, but I didn't want to assign it there in case
            # there was some kind of exception here that would prevent the
            # rest of the state from being correct.
            # This function should be cheap by design anyway.
            if etag_function is not None:
                state.server_etag = etag_function()

            state.last_run = time.monotonic()
            return value

        log.debug('Decorating %s with cached_endpoint.', function)

        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            # Should I use a threading.Lock to prevent two simultaneous requests
            # from running the expensive function, and force one of them to
            # wait for the other to finish?

            state_key = (request.path, tuple(sorted(request.args.items())))
            state = states.get(state_key)

            exists = (state is not None)
            if not exists:
                state = new_state()

            if not can_reuse_state(state):
                update_state(state, *args, **kwargs)

            client_etag = request.headers.get('If-None-Match', None)
            # log.debug('client_etag=%s state.client_etag=%s', client_etag, state.client_etag)
            if client_etag == state.client_etag:
                response = flask.Response(status=304, headers=state.headers)
            else:
                response = flask.Response(state.stored_value, status=200, headers=state.headers)

            if not exists and response.status_code in {200, 304}:
                states[state_key] = state

            return response
        return wrapped
    return wrapper

def decorate_and_route(flask_app, decorators):
    '''
    Flask provides decorators for before_request and after_request, but not for
    wrapping the whole request. Sometimes I want to wrap the whole request,
    either to catch exceptions (which don't get passed through after_request)
    or to maintain some state before running the function and adding it to the
    response after.

    Instead of pasting my decorators onto every single endpoint and forgetting
    to keep up with them in the future, we can just hijack the decorator I know
    every endpoint will have: route.

    You should set:
    flask_app.route = flasktools.decorate_and_route(flask_app, decorators[...])

    So every time your route something, it will also get the other decorators.
    '''
    old_route = flask_app.route
    @functools.wraps(old_route)
    def new_route(*route_args, **route_kwargs):
        def wrapper(endpoint):
            # Since a single endpoint function can have multiple route
            # decorators on it, we might see the same function come through
            # here multiple times. We'll only do the user's decorators once.
            if not hasattr(endpoint, '_fully_decorated'):
                for decorator in decorators:
                    endpoint = decorator(endpoint)
                endpoint._fully_decorated = True

            endpoint = old_route(*route_args, **route_kwargs)(endpoint)
            return endpoint
        return wrapper
    return new_route

def ensure_response_type(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        response = function(*args, **kwargs)
        if not isinstance(response, RESPONSE_TYPES):
            response = flask.Response(response)
        return response
    return wrapped

def give_theme_cookie(function, *, cookie_name, default_theme):
    '''
    This decorator is one component of a theming system, where the user gets a
    CSS stylesheet based on the value of their theme cookie.

    Add this decorator to your endpoint. Then, use request.cookies.get to
    check what theme they want. This decorator will inject the cookie before
    your function runs. Add the appropriate stylesheet to your response HTML.

    The user can change their theme by adding ?theme=name to the end of any URL
    which uses this decorator.
    '''
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        old_theme = request.cookies.get(cookie_name, None)
        new_theme = request.args.get('theme', None)
        if new_theme is not None and any(badchar in new_theme for badchar in {'..', '/', '\\'}):
            new_theme = None
        theme = new_theme or old_theme or default_theme

        # The original data structure for request.cookies is immutable and we
        # must turn it into this multidict.
        request.cookies = werkzeug.datastructures.MultiDict(request.cookies)
        # By injecting the cookie here, we allow the endpoint function to check
        # request.cookies even if the client didn't actually have one when they
        # started the request.
        request.cookies[cookie_name] = theme

        response = function(*args, **kwargs)

        if new_theme is None:
            pass
        elif new_theme == '':
            response.set_cookie(cookie_name, value='', expires=0)
        elif new_theme != old_theme:
            response.set_cookie(cookie_name, value=new_theme, expires=2147483647)

        return response
    return wrapped

def gzip_response(request, response):
    if response.direct_passthrough:
        return response

    accept_encoding = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept_encoding.lower():
        return response

    if 'Content-Encoding' in response.headers:
        return response

    content_type = response.headers.get('Content-Type', '')
    if not (content_type.startswith('application/json') or content_type.startswith('text/')):
        return response

    if response.status_code < 200:
        return response

    if response.status_code >= 300:
        return response

    content_length = response.headers.get('Content-Length', None)
    if content_length is not None and int(content_length) > GZIP_MAXIMUM_SIZE:
        return response

    if content_length is not None and int(content_length) < GZIP_MINIMUM_SIZE:
        return response

    gzip_buffer = io.BytesIO()
    gzip_file = gzip.GzipFile(mode='wb', compresslevel=GZIP_LEVEL, fileobj=gzip_buffer)
    gzip_file.write(response.get_data())
    gzip_file.close()
    response.set_data(gzip_buffer.getvalue())
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.get_data())

    return response

def atom_response(soup, *args, **kwargs):
    response = flask.Response(str(soup), *args, **kwargs)
    response.headers['Content-Type'] = 'application/atom+xml;charset=utf-8',
    return response

def json_response(j, *args, **kwargs):
    dumped = json.dumps(j)
    response = flask.Response(dumped, *args, **kwargs)
    response.headers['Content-Type'] = 'application/json;charset=utf-8'
    return response

make_json_response = json_response

def required_fields(fields, forbid_whitespace=False):
    '''
    Declare that the endpoint requires certain POST body fields. Without them,
    we respond with 400 and a message.

    forbid_whitespace:
        If True, then providing the field is not good enough. It must also
        contain at least some non-whitespace characters.
    '''
    def wrapper(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            for requirement in fields:
                missing = (
                    requirement not in request.form or
                    (forbid_whitespace and request.form[requirement].strip() == '')
                )
                if missing:
                    response = {
                        'type': 'error',
                        'error_type': 'MISSING_FIELDS',
                        'error_message': 'Required fields: %s' % ', '.join(fields),
                    }
                    response = json_response(response, status=400)
                    return response
            return function(*args, **kwargs)
        return wrapped
    return wrapper

def send_sse(*, event, data):
    # This is not required by spec, but it is required for my sanity.
    # I think every message should be describable by some event name.
    if event is None:
        raise TypeError(event)

    event = event.strip()
    if not event:
        raise ValueError(event)

    message = [f'event: {event}']

    if data is None or data == '':
        message.append('data: ')
    else:
        data = str(data)
        data = '\n'.join(f'data: {line.strip()}' for line in data.splitlines())
        message.append(data)

    message = '\n'.join(message) + '\n\n'
    message = message.encode('utf-8')

    with SSE_LISTENERS_LOCK:
        for queue in SSE_LISTENERS:
            queue.put(message)

def send_sse_comment(comment):
    message = f': {comment}\n\n'
    message = message.encode('utf-8')
    with SSE_LISTENERS_LOCK:
        for queue in SSE_LISTENERS:
            queue.put(message)

def sse_generator():
    this_queue = queue.Queue()
    with SSE_LISTENERS_LOCK:
        SSE_LISTENERS.add(this_queue)
    try:
        log.debug('SSE listener has connected.')
        yield ': welcome\n\n'.encode('utf-8')
        while True:
            try:
                message = this_queue.get(timeout=60)
                yield message
            except queue.Empty:
                pass
    except GeneratorExit:
        log.debug('SSE listener has disconnected.')
        with SSE_LISTENERS_LOCK:
            SSE_LISTENERS.remove(this_queue)
