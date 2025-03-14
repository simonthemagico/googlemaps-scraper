import base64
import ctypes
import urllib
from json import dumps, loads
from tls_client import Session
from tls_client.response import Response
from tls_client.cookies import merge_cookies, extract_cookies_to_jar
from tls_client.response import build_response
from tls_client.exceptions import TLSClientExeption
from tls_client.structures import CaseInsensitiveDict
from tls_client.settings import ClientIdentifiers
from tls_client.cffi import request, freeMemory
from monseigneur.core.browser.pages import HTMLPage
from monseigneur.core.browser.url import URL
from monseigneur.core.browser.browsers import DomainBrowser
from monseigneur.core.browser.exceptions import UrlNotAllowed
from monseigneur.core.browser.request import Request
from collections import OrderedDict
from copy import deepcopy
from typing import Dict, List, Optional, Union
from requests.status_codes import _codes
from requests.exceptions import HTTPError
from requests.models import Response as RequestResponse

def raise_for_status(self: RequestResponse):
    """Raises :class:`HTTPError`, if one occurred."""

    http_error_msg = ""
    if isinstance(self.reason, bytes):
        # We attempt to decode utf-8 first because some servers
        # choose to localize their reason strings. If the string
        # isn't utf-8, we fall back to iso-8859-1 for all other
        # encodings. (See PR #3538)
        try:
            reason = self.reason.decode("utf-8")
        except UnicodeDecodeError:
            reason = self.reason.decode("iso-8859-1")
    else:
        reason = self.reason

    if 400 <= self.status_code < 500:
        http_error_msg = (
            f"{self.status_code} Client Error: {reason} for url: {self.url}"
        )

    elif 500 <= self.status_code < 600:
        http_error_msg = (
            f"{self.status_code} Server Error: {reason} for url: {self.url}"
        )

    if http_error_msg:
        raise HTTPError(http_error_msg, response=self)

class TLSSession(Session):

    def execute_request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,  # Optional[dict[str, str]]
        data: Optional[Union[str, dict]] = None,
        headers: Optional[dict] = None,  # Optional[dict[str, str]]
        cookies: Optional[dict] = None,  # Optional[dict[str, str]]
        json: Optional[dict] = None,  # Optional[dict]
        allow_redirects: Optional[bool] = False,
        insecure_skip_verify: Optional[bool] = False,
        timeout_seconds: Optional[int] = None,
        proxy: Optional[dict] = None  # Optional[dict[str, str]]
    ) -> Response:
        # --- URL ------------------------------------------------------------------------------------------------------
        # Prepare URL - add params to url
        if params is not None:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"

        # --- Request Body ---------------------------------------------------------------------------------------------
        # Prepare request body - build request body
        # Data has priority. JSON is only used if data is None.
        if data is None and json is not None:
            if type(json) in [dict, list]:
                json = dumps(json)
            request_body = json
            content_type = "application/json"
        elif data is not None and type(data) not in [str, bytes]:
            request_body = urllib.parse.urlencode(data, doseq=True)
            content_type = "application/x-www-form-urlencoded"
        else:
            request_body = data
            content_type = None
        # set content type if it isn't set
        if content_type is not None and "content-type" not in self.headers:
            self.headers["Content-Type"] = content_type

        # --- Headers --------------------------------------------------------------------------------------------------
        if self.headers is None:
            headers = CaseInsensitiveDict(headers)
        elif headers is None:
            headers = self.headers
        else:
            merged_headers = CaseInsensitiveDict(self.headers)
            merged_headers.update(headers)

            # Remove items, where the key or value is set to None.
            none_keys = [k for (k, v) in merged_headers.items() if v is None or k is None]
            for key in none_keys:
                del merged_headers[key]

            headers = merged_headers

        # --- Cookies --------------------------------------------------------------------------------------------------
        cookies = cookies or {}
        # Merge with session cookies
        cookies = merge_cookies(self.cookies, cookies)
        # turn cookie jar into dict
        # in the cookie value the " gets removed, because the fhttp library in golang doesn't accept the character
        request_cookies = [
            {'domain': c.domain, 'expires': c.expires, 'name': c.name, 'path': c.path, 'value': c.value.replace('"', "")}
            for c in cookies
        ]

        # --- Proxy ----------------------------------------------------------------------------------------------------
        proxy = proxy or self.proxies
        
        if type(proxy) is dict and "http" in proxy:
            proxy = proxy["http"]
        elif type(proxy) is str:
            proxy = proxy
        else:
            proxy = ""

        # --- Timeout --------------------------------------------------------------------------------------------------
        # maximum time to wait for a response

        timeout_seconds = timeout_seconds or self.timeout_seconds

        # --- Certificate pinning --------------------------------------------------------------------------------------
        # pins a certificate so that it restricts which certificates are considered valid

        certificate_pinning = self.certificate_pinning
        
        # --- Request --------------------------------------------------------------------------------------------------
        is_byte_request = isinstance(request_body, (bytes, bytearray))
        request_payload = {
            "sessionId": self._session_id,
            "followRedirects": allow_redirects,
            "forceHttp1": self.force_http1,
            "withDebug": self.debug,
            "catchPanics": self.catch_panics,
            "headers": dict(headers),
            "headerOrder": self.header_order,
            "insecureSkipVerify": insecure_skip_verify,
            "isByteRequest": is_byte_request,
            "additionalDecode": self.additional_decode,
            "proxyUrl": proxy,
            "requestUrl": url,
            "requestMethod": method,
            "requestBody": base64.b64encode(request_body).decode() if is_byte_request else request_body,
            "requestCookies": request_cookies,
            "timeoutSeconds": timeout_seconds,
        }
        if certificate_pinning:
            request_payload["certificatePinningHosts"] = certificate_pinning
        if self.client_identifier is None:
            request_payload["customTlsClient"] = {
                "ja3String": self.ja3_string,
                "h2Settings": self.h2_settings,
                "h2SettingsOrder": self.h2_settings_order,
                "pseudoHeaderOrder": self.pseudo_header_order,
                "connectionFlow": self.connection_flow,
                "priorityFrames": self.priority_frames,
                "headerPriority": self.header_priority,
                "certCompressionAlgo": self.cert_compression_algo,
                "supportedVersions": self.supported_versions,
                "supportedSignatureAlgorithms": self.supported_signature_algorithms,
                "supportedDelegatedCredentialsAlgorithms": self.supported_delegated_credentials_algorithms ,
                "keyShareCurves": self.key_share_curves,
            }
        else:
            request_payload["tlsClientIdentifier"] = self.client_identifier
            request_payload["withRandomTLSExtensionOrder"] = self.random_tls_extension_order

        request_obj = Request(request_payload)

        # this is a pointer to the response
        response = request(dumps(request_payload).encode('utf-8'))
        # dereference the pointer to a byte array
        response_bytes = ctypes.string_at(response)
        # convert our byte array to a string (tls client returns json)
        response_string = response_bytes.decode('utf-8')
        # convert response string to json
        response_object = loads(response_string)
        # free the memory
        freeMemory(response_object['id'].encode('utf-8'))
        # --- Response -------------------------------------------------------------------------------------------------
        # Error handling
        if response_object["status"] == 0:
            raise TLSClientExeption(response_object["body"])
        # Set response cookies
        response_cookie_jar = extract_cookies_to_jar(
            request_url=url,
            request_headers=headers,
            cookie_jar=cookies,
            response_headers=response_object["headers"]
        )
        # build response class
        response_obj = build_response(response_object, response_cookie_jar)
        response_obj.encoding = 'utf-8'
        response_obj.elapsed = object()
        response_obj.request = request_obj
        response_obj.reason = _codes[response_obj.status_code][0]
        response_obj.raise_for_status = lambda: raise_for_status(response_obj)
        return response_obj

class TLSClientBrowser(DomainBrowser):
    BASEURL = None
    RESTRICT_URL = False
    _urls = None
    
    client_identifier: str = "chrome_120"
    ja3_string: Optional[str] = None
    h2_settings: Optional[Dict[str, int]] = None
    h2_settings_order: Optional[List[str]] = None
    supported_signature_algorithms: Optional[List[str]] = None
    supported_delegated_credentials_algorithms: Optional[List[str]] = None
    supported_versions: Optional[List[str]] = None
    key_share_curves: Optional[List[str]] = None
    cert_compression_algo: str = None
    additional_decode: str = None
    pseudo_header_order: Optional[List[str]] = None
    connection_flow: Optional[int] = None
    priority_frames: Optional[list] = None
    header_order: Optional[List[str]] = None
    header_priority: Optional[List[str]] = None
    random_tls_extension_order = False
    force_http1 = False
    catch_panics = False
    debug = False
    certificate_pinning: Optional[Dict[str, List[str]]] = None

    def __init__(self, baseurl=None, *args, **kwargs):
        super(TLSClientBrowser, self).__init__(*args, **kwargs)
        if baseurl is not None:
            self.BASEURL = baseurl

        self.page = None

        # Collect URL objects
        def is_property(attr):
            v = getattr(type(self), attr, None)
            return hasattr(v, '__get__') or hasattr(v, '__set__')

        attrs = [(attr, getattr(self, attr)) for attr in dir(self) if not is_property(attr)]
        attrs = [v for v in attrs if isinstance(v[1], URL)]
        attrs.sort(key=lambda v: v[1]._creation_counter)
        self._urls = OrderedDict(deepcopy(attrs))
        for k, v in self._urls.items():
            setattr(self, k, v)
        for url in self._urls.values():
            url.browser = self
    
    @property
    def PROXIES(self):
        return self.session.proxies

    @PROXIES.setter
    def PROXIES(self, value):
        self.session.proxies = value

    def _create_session(self):
        return TLSSession(
            client_identifier=self.client_identifier,
            ja3_string=self.ja3_string,
            h2_settings=self.h2_settings,
            h2_settings_order=self.h2_settings_order,
            supported_signature_algorithms=self.supported_signature_algorithms,
            supported_delegated_credentials_algorithms=self.supported_delegated_credentials_algorithms,
            supported_versions=self.supported_versions,
            key_share_curves=self.key_share_curves,
            cert_compression_algo=self.cert_compression_algo,
            additional_decode=self.additional_decode,
            pseudo_header_order=self.pseudo_header_order,
            connection_flow=self.connection_flow,
            priority_frames=self.priority_frames,
            header_order=self.header_order,
            header_priority=self.header_priority,
            random_tls_extension_order=self.random_tls_extension_order,
            force_http1=self.force_http1,
            catch_panics=self.catch_panics,
            debug=self.debug,
            certificate_pinning=self.certificate_pinning,
        )

    def open(self, req, *args, **kwargs):
        uri = req if isinstance(req, str) else req.url
        url = self.absurl(uri)
        if not self.url_allowed(url):
            raise UrlNotAllowed(url)

        if isinstance(req, str):
            req = url
        else:
            req.url = url
        method = kwargs.get('method') if isinstance(req, str) else req.method
        if not method:
            kwargs['method'] = 'GET'
        kwargs['insecure_skip_verify'] = not kwargs.pop('verify', False)
        for key in ['pause', 'auth', 'referrer']:
            kwargs.pop(key, None)
        self.current_url = url
        response = self.session.execute_request(url=req, **kwargs)
        self.response = response
        self.save_response(response)
        self.raise_for_status(response)
        self.refresh_handle(response)
        self.url = response.url
        return response

    def location(self, *args, **kwargs):
        if self.page is not None:
            self.page.on_leave()
        response = self.open(*args, **kwargs)
        self.page = response.page if hasattr(response, 'page') else None
        self.url = response.url
        if self.page is not None:
            self.page.on_load()
        return response

    def refresh_handle(self, response):
        response.page = None
        response.encoding = 'utf-8'
        for url in self._urls.values():
            response.page = url.handle(response)
            if response.page is not None:
                self.logger.debug('Handle %s with %s', response.url, response.page.__class__.__name__)
                break

        if response.page is None:
            self.logger.warning('Unable to handle %s', response.url)

        self.page = response.page

if __name__ == '__main__':
    # Example Usage
    class MyTLSClientBrowser(TLSClientBrowser):
        BASEURL = 'https://api.ipify.org'
        ip = URL('/', HTMLPage)

    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Usage
    browser = MyTLSClientBrowser()
    response = browser.ip.stay_or_go()
    print(response.text)
