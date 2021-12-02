import time

from .static import TIME, DEFAULT_TIMEOUT
from .logz import get_logger
logger = get_logger()

"""
Rancher API Specific Utilities
"""

def convert_type_name(type):
    if isinstance(type, str) is True: return type.replace(".", "_").replace("-", "")
    return type

def create_clskey(apiVersion: str, modulename: str = 'Rke'):
    if '/v' in apiVersion:
        apiname, apiver = apiVersion.split('/', 1)
        apiname = ''.join([i for i in apiname.replace('-', '_').split('.')])
        return f'{modulename}{apiname.capitalize()}_{apiver}'
    apiname = ''.join([i for i in apiVersion.replace('-', '_').split('.')])
    return f'{modulename}{apiname.capitalize()}'


def timed_url(fn):
    def wrapped(*args, **kw):
        if not TIME: return fn(*args, **kw)
        start = time.time()
        ret = fn(*args, **kw)
        delta = time.time() - start
        logger.info(f'{delta} {args[1]} {fn.__name__}')
        return ret
    return wrapped

def async_timed_url(fn):
    async def wrapped(*args, **kw):
        if not TIME: return await fn(*args, **kw)
        start = time.time()
        ret = await fn(*args, **kw)
        delta = time.time() - start
        logger.info(f'{delta} {args[1]} {fn.__name__}')
        return ret
    return wrapped

def _get_timeout(timeout):
    if timeout == -1: return DEFAULT_TIMEOUT
    return timeout

__all__ = [
    'convert_type_name',
    'create_clskey',
    'timed_url',
    'async_timed_url',
    '_get_timeout',
    'logger'
]
