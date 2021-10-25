'''
This module provides individual exception classes for all HTTP statuses between
400 and 599. This makes try/catch code involving status codes easier to look at.
Instead of:

try:
    ...
except requests.exceptions.ConnectionError:
    ...
except requests.exceptions.Timeout:
    ...
except requests.exceptions.HTTPError as exc:
    if exc.status_code >= 500:
        ...
    elif exc.status_code == 403:
        ...

we can write:

try:
    ...
except requests.exceptions.ConnectionError:
    ...
except requests.exceptions.Timeout:
    ...
except httperrors.HTTP5XX:
    ...
except httperrors.HTTP403:
    ...

with more harmonious indentation.

All of these exceptions inherit from requests.exceptions.HTTPError, so existing
code will not be affected.
'''
import requests

class HTTP4XX(requests.exceptions.HTTPError): pass
class HTTP400(HTTP4XX): pass
class HTTP401(HTTP4XX): pass
class HTTP402(HTTP4XX): pass
class HTTP403(HTTP4XX): pass
class HTTP404(HTTP4XX): pass
class HTTP405(HTTP4XX): pass
class HTTP406(HTTP4XX): pass
class HTTP407(HTTP4XX): pass
class HTTP408(HTTP4XX): pass
class HTTP409(HTTP4XX): pass
class HTTP410(HTTP4XX): pass
class HTTP411(HTTP4XX): pass
class HTTP412(HTTP4XX): pass
class HTTP413(HTTP4XX): pass
class HTTP414(HTTP4XX): pass
class HTTP415(HTTP4XX): pass
class HTTP416(HTTP4XX): pass
class HTTP417(HTTP4XX): pass
class HTTP418(HTTP4XX): pass
class HTTP419(HTTP4XX): pass
class HTTP420(HTTP4XX): pass
class HTTP421(HTTP4XX): pass
class HTTP422(HTTP4XX): pass
class HTTP423(HTTP4XX): pass
class HTTP424(HTTP4XX): pass
class HTTP425(HTTP4XX): pass
class HTTP426(HTTP4XX): pass
class HTTP427(HTTP4XX): pass
class HTTP428(HTTP4XX): pass
class HTTP429(HTTP4XX): pass
class HTTP430(HTTP4XX): pass
class HTTP431(HTTP4XX): pass
class HTTP432(HTTP4XX): pass
class HTTP433(HTTP4XX): pass
class HTTP434(HTTP4XX): pass
class HTTP435(HTTP4XX): pass
class HTTP436(HTTP4XX): pass
class HTTP437(HTTP4XX): pass
class HTTP438(HTTP4XX): pass
class HTTP439(HTTP4XX): pass
class HTTP440(HTTP4XX): pass
class HTTP441(HTTP4XX): pass
class HTTP442(HTTP4XX): pass
class HTTP443(HTTP4XX): pass
class HTTP444(HTTP4XX): pass
class HTTP445(HTTP4XX): pass
class HTTP446(HTTP4XX): pass
class HTTP447(HTTP4XX): pass
class HTTP448(HTTP4XX): pass
class HTTP449(HTTP4XX): pass
class HTTP450(HTTP4XX): pass
class HTTP451(HTTP4XX): pass
class HTTP452(HTTP4XX): pass
class HTTP453(HTTP4XX): pass
class HTTP454(HTTP4XX): pass
class HTTP455(HTTP4XX): pass
class HTTP456(HTTP4XX): pass
class HTTP457(HTTP4XX): pass
class HTTP458(HTTP4XX): pass
class HTTP459(HTTP4XX): pass
class HTTP460(HTTP4XX): pass
class HTTP461(HTTP4XX): pass
class HTTP462(HTTP4XX): pass
class HTTP463(HTTP4XX): pass
class HTTP464(HTTP4XX): pass
class HTTP465(HTTP4XX): pass
class HTTP466(HTTP4XX): pass
class HTTP467(HTTP4XX): pass
class HTTP468(HTTP4XX): pass
class HTTP469(HTTP4XX): pass
class HTTP470(HTTP4XX): pass
class HTTP471(HTTP4XX): pass
class HTTP472(HTTP4XX): pass
class HTTP473(HTTP4XX): pass
class HTTP474(HTTP4XX): pass
class HTTP475(HTTP4XX): pass
class HTTP476(HTTP4XX): pass
class HTTP477(HTTP4XX): pass
class HTTP478(HTTP4XX): pass
class HTTP479(HTTP4XX): pass
class HTTP480(HTTP4XX): pass
class HTTP481(HTTP4XX): pass
class HTTP482(HTTP4XX): pass
class HTTP483(HTTP4XX): pass
class HTTP484(HTTP4XX): pass
class HTTP485(HTTP4XX): pass
class HTTP486(HTTP4XX): pass
class HTTP487(HTTP4XX): pass
class HTTP488(HTTP4XX): pass
class HTTP489(HTTP4XX): pass
class HTTP490(HTTP4XX): pass
class HTTP491(HTTP4XX): pass
class HTTP492(HTTP4XX): pass
class HTTP493(HTTP4XX): pass
class HTTP494(HTTP4XX): pass
class HTTP495(HTTP4XX): pass
class HTTP496(HTTP4XX): pass
class HTTP497(HTTP4XX): pass
class HTTP498(HTTP4XX): pass
class HTTP499(HTTP4XX): pass

class HTTP5XX(requests.exceptions.HTTPError): pass
class HTTP500(HTTP5XX): pass
class HTTP501(HTTP5XX): pass
class HTTP502(HTTP5XX): pass
class HTTP503(HTTP5XX): pass
class HTTP504(HTTP5XX): pass
class HTTP505(HTTP5XX): pass
class HTTP506(HTTP5XX): pass
class HTTP507(HTTP5XX): pass
class HTTP508(HTTP5XX): pass
class HTTP509(HTTP5XX): pass
class HTTP510(HTTP5XX): pass
class HTTP511(HTTP5XX): pass
class HTTP512(HTTP5XX): pass
class HTTP513(HTTP5XX): pass
class HTTP514(HTTP5XX): pass
class HTTP515(HTTP5XX): pass
class HTTP516(HTTP5XX): pass
class HTTP517(HTTP5XX): pass
class HTTP518(HTTP5XX): pass
class HTTP519(HTTP5XX): pass
class HTTP520(HTTP5XX): pass
class HTTP521(HTTP5XX): pass
class HTTP522(HTTP5XX): pass
class HTTP523(HTTP5XX): pass
class HTTP524(HTTP5XX): pass
class HTTP525(HTTP5XX): pass
class HTTP526(HTTP5XX): pass
class HTTP527(HTTP5XX): pass
class HTTP528(HTTP5XX): pass
class HTTP529(HTTP5XX): pass
class HTTP530(HTTP5XX): pass
class HTTP531(HTTP5XX): pass
class HTTP532(HTTP5XX): pass
class HTTP533(HTTP5XX): pass
class HTTP534(HTTP5XX): pass
class HTTP535(HTTP5XX): pass
class HTTP536(HTTP5XX): pass
class HTTP537(HTTP5XX): pass
class HTTP538(HTTP5XX): pass
class HTTP539(HTTP5XX): pass
class HTTP540(HTTP5XX): pass
class HTTP541(HTTP5XX): pass
class HTTP542(HTTP5XX): pass
class HTTP543(HTTP5XX): pass
class HTTP544(HTTP5XX): pass
class HTTP545(HTTP5XX): pass
class HTTP546(HTTP5XX): pass
class HTTP547(HTTP5XX): pass
class HTTP548(HTTP5XX): pass
class HTTP549(HTTP5XX): pass
class HTTP550(HTTP5XX): pass
class HTTP551(HTTP5XX): pass
class HTTP552(HTTP5XX): pass
class HTTP553(HTTP5XX): pass
class HTTP554(HTTP5XX): pass
class HTTP555(HTTP5XX): pass
class HTTP556(HTTP5XX): pass
class HTTP557(HTTP5XX): pass
class HTTP558(HTTP5XX): pass
class HTTP559(HTTP5XX): pass
class HTTP560(HTTP5XX): pass
class HTTP561(HTTP5XX): pass
class HTTP562(HTTP5XX): pass
class HTTP563(HTTP5XX): pass
class HTTP564(HTTP5XX): pass
class HTTP565(HTTP5XX): pass
class HTTP566(HTTP5XX): pass
class HTTP567(HTTP5XX): pass
class HTTP568(HTTP5XX): pass
class HTTP569(HTTP5XX): pass
class HTTP570(HTTP5XX): pass
class HTTP571(HTTP5XX): pass
class HTTP572(HTTP5XX): pass
class HTTP573(HTTP5XX): pass
class HTTP574(HTTP5XX): pass
class HTTP575(HTTP5XX): pass
class HTTP576(HTTP5XX): pass
class HTTP577(HTTP5XX): pass
class HTTP578(HTTP5XX): pass
class HTTP579(HTTP5XX): pass
class HTTP580(HTTP5XX): pass
class HTTP581(HTTP5XX): pass
class HTTP582(HTTP5XX): pass
class HTTP583(HTTP5XX): pass
class HTTP584(HTTP5XX): pass
class HTTP585(HTTP5XX): pass
class HTTP586(HTTP5XX): pass
class HTTP587(HTTP5XX): pass
class HTTP588(HTTP5XX): pass
class HTTP589(HTTP5XX): pass
class HTTP590(HTTP5XX): pass
class HTTP591(HTTP5XX): pass
class HTTP592(HTTP5XX): pass
class HTTP593(HTTP5XX): pass
class HTTP594(HTTP5XX): pass
class HTTP595(HTTP5XX): pass
class HTTP596(HTTP5XX): pass
class HTTP597(HTTP5XX): pass
class HTTP598(HTTP5XX): pass
class HTTP599(HTTP5XX): pass

_requests_raise_for_status = requests.Response.raise_for_status

def monkeypatch_requests():
    '''
    This function will replace requests.Response.raise_for_status with our
    function. You can use this if one of your dependency modules uses requests
    and raises HTTPErrors, but you want it to raise these errors instead.
    '''
    import requests
    requests.Response.raise_for_status = raise_for_status

def raise_for_status(response):
    try:
        _requests_raise_for_status(response)
    except requests.exceptions.HTTPError as exc:
        cls = globals().get(f'HTTP{response.status_code}', None)
        if not cls:
            raise

        new_exc = cls(request=exc.request,response=exc.response)
        raise new_exc from exc
