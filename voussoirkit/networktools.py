import requests
import socket

from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'networktools')

def get_external_ip():
    url = 'https://voussoir.net/whatsmyip'
    response = requests.get(url)
    response.raise_for_status()
    ip = response.text.strip()
    return ip

def get_lan_ip():
    '''
    thank you unknwntech
    https://stackoverflow.com/a/166589
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(('8.8.8.8', 80))
    return sock.getsockname()[0]

def get_gateway_ip():
    # How to find ip of the router?
    raise NotImplementedError

def has_lan():
    # Open a socket to the router
    raise NotImplementedError

def has_internet(timeout=2):
    socket.setdefaulttimeout(timeout)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('8.8.8.8', 53))
        return True
    except socket.error as exc:
        return False
