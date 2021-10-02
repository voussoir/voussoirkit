import flask; from flask import request
import functools
import gzip
import io
import json
import time
import werkzeug.wrappers

from voussoirkit import bytestring
from voussoirkit import dotdict
from voussoirkit import passwordy
from voussoirkit import sentinel

GZIP_MINIMUM_SIZE = 500 * bytestring.BYTE
GZIP_MAXIMUM_SIZE = 5 * bytestring.MIBIBYTE
GZIP_LEVEL = 3

REQUEST_TYPES = (flask.Request, werkzeug.wrappers.Request, werkzeug.local.LocalProxy)
RESPONSE_TYPES = (flask.Response, werkzeug.wrappers.Response)

NOT_CACHED = sentinel.Sentinel('not cached', truthyness=False)

def cached_endpoint(max_age):
    '''
    The cached_endpoint decorator can be used on slow endpoints that don't need
    to be constantly updated or endpoints that produce large, static responses.

    WARNING: The return value of the endpoint is shared with all users.
    You should never use this cache on an endpoint that provides private
    or personalized data, and you should not try to pass other headers through
    the response.

    When the function is run, its return value is stored and a random etag is
    generated so that subsequent runs can respond with 304. This way, large
    response bodies do not need to be transmitted often.

    Given a nonzero max_age, the endpoint will only be run once per max_age
    seconds on a global basis (not per-user). This way, you can prevent a slow
    function from being run very often. In-between requests will just receive
    the previous return value (still using 200 or 304 as appropriate for the
    client's provided etag).

    With max_age=0, the function will be run every time to check if the value
    has changed, but if it hasn't changed then we can still send a 304 response,
    saving bandwidth.

    An example use case would be large-sized data dumps that don't need to be
    precisely up to date every time.
    '''
    if max_age < 0:
        raise ValueError(f'max_age should be positive, not {max_age}.')

    state = dotdict.DotDict({
        'max_age': max_age,
        'stored_value': NOT_CACHED,
        'stored_etag': None,
        'headers': {'ETag': None, 'Cache-Control': f'max-age={max_age}'},
        'last_run': 0,
    })

    def wrapper(function):
        def get_value(*args, **kwargs):
            can_bail = (
                state.stored_value is not NOT_CACHED and
                state.max_age != 0 and
                (time.time() - state.last_run) < state.max_age
            )
            if can_bail:
                return state.stored_value

            value = function(*args, **kwargs)
            if isinstance(value, flask.Response):
                if value.headers.get('Content-Type'):
                    state.headers['Content-Type'] = value.headers.get('Content-Type')
                value = value.response

            if value != state.stored_value:
                state.stored_value = value
                state.stored_etag = passwordy.random_hex(20)
                state.headers['ETag'] = state.stored_etag

            state.last_run = time.time()
            return value

        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            value = get_value(*args, **kwargs)

            client_etag = request.headers.get('If-None-Match', None)
            if client_etag == state.stored_etag:
                response = flask.Response(status=304, headers=state.headers)
            else:
                response = flask.Response(value, status=200, headers=state.headers)

            return response
        return wrapped
    return wrapper

def ensure_response_type(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        response = function(*args, **kwargs)
        if not isinstance(response, RESPONSE_TYPES):
            response = flask.Response(response)
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
