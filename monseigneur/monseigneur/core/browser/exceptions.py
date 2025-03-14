# -*- coding: utf-8 -*-

from requests.exceptions import HTTPError
from monseigneur.monseigneur.core.exceptions import BrowserHTTPError, BrowserHTTPNotFound


class HTTPNotFound(HTTPError, BrowserHTTPNotFound):
    pass


class ClientError(HTTPError, BrowserHTTPError):
    pass


class ServerError(HTTPError, BrowserHTTPError):
    pass


class ReadTimeoutError(HTTPError, BrowserHTTPError):
    pass


class LoggedOut(Exception):
    pass


class PycurlStreamError(Exception):
    pass


class PyCurlRewindError(Exception):
    pass

class PyCurlEncodingError(Exception):
    pass

class ProxyResolveError(Exception):
    pass


class IllegalURLError(Exception):
    pass


class ProxyError(Exception):
    pass


class Http2Error(Exception):
    pass


class SelfSignedError(Exception):
    pass


class TooManyRedirects(Exception):
    pass


class EmptyReplyError(Exception):
    pass

class UrlNotAllowed(Exception):
    pass
