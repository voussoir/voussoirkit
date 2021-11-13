'''
networktools
============

This module provides functions for learning the current network status and
internal / external IP addresses.
'''
import requests
import socket
import time

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
    response.raise_for_status()
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
    Return True if an internet connection is available.
    '''
    socket.setdefaulttimeout(timeout)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((INTERNET_IP, 53))
        return True
    except socket.error as exc:
        return False

def wait_for_internet(timeout) -> None:
    '''
    This function blocks until an internet connection is available, or the
    timeout is reached.

    Raises NoInternet if the timeout expires.
    '''
    if timeout <= 0:
        raise ValueError(f'timeout should be greater than 0, not {timeout}.')

    started = time.time()
    while True:
        if time.time() - started >= timeout:
            raise NoInternet()
        if has_internet(timeout=1):
            return
