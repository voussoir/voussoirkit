import flask
import functools
import gzip
import io
import werkzeug.wrappers

from voussoirkit import bytestring

GZIP_MINIMUM_SIZE = 500 * bytestring.BYTE
GZIP_MAXIMUM_SIZE = 5 * bytestring.MIBIBYTE
GZIP_LEVEL = 3

REQUEST_TYPES = (flask.Request, werkzeug.wrappers.Request, werkzeug.local.LocalProxy)
RESPONSE_TYPES = (flask.Response, werkzeug.wrappers.Response)

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
