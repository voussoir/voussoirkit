'''
networktools
============

This module provides functions for learning the current network status and
internal / external IP addresses.
'''
import requests
import socket
import time

from voussoirkit import httperrors
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'networktools')

# This is the IP address we'll use to determine if we have an internet
# connection. Change it if this server ever becomes unavailable.
INTERNET_IP = '8.8.8.8'

class NetworkToolsException(Exception):
    pass

class NoInternet(NetworkToolsException):
    pass

def get_external_ip(timeout=10) -> str:
    url = 'https://voussoir.net/whatsmyip'
    response = requests.get(url, timeout=timeout)
    httperrors.raise_for_status(response)
    ip = response.text.strip()
    return ip

def get_lan_ip() -> str:
    '''
    thank you unknwntech
    https://stackoverflow.com/a/166589
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((INTERNET_IP, 80))
    return sock.getsockname()[0]

def get_gateway_ip():
    # How to find ip of the router?
    raise NotImplementedError

def has_lan():
    # Open a socket to the router
    raise NotImplementedError

def has_internet(timeout=2) -> bool:
    '''
    Return True if an internet connection is available. Returns False if the
    timeout expires.
    '''
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((INTERNET_IP, 53))
        return True
    except socket.error as exc:
        return False

def wait_for_internet(timeout, *, backoff=None) -> None:
    '''
    This function blocks until an internet connection is available, or the
    timeout is reached.

    timeout:
        Number of seconds after which we raise NoInternet.

    backoff:
        You can provide an instance of a voussoirkit.backoff class to introduce
        sleeps between each internet check. This can help reduce busywaiting at
        the expense of not getting the earliest possible return.

        If None, there will be no sleeps between checks, though there is still
        a timeout on each individual check.

    Raises NoInternet if the timeout expires.
    '''
    if timeout <= 0:
        raise ValueError(f'timeout should be greater than 0, not {timeout}.')

    started = time.time()
    while True:
        if has_internet(timeout=2):
            return
        if time.time() - started >= timeout:
            raise NoInternet()
        if backoff is not None:
            time.sleep(backoff.next())
