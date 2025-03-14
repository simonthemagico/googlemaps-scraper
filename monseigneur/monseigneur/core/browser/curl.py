# for browsing
from collections import OrderedDict
from copy import deepcopy
import json as pjson
import pycurl
import sys
import os
import glob
import signal
from celery.utils.log import get_task_logger

# for refresh handle
import re
from monseigneur.core.exceptions import BrowserHTTPSDowngrade, BrowserSSLError, ConnectionResetByPeer
from monseigneur.core.browser.exceptions import ClientError, EmptyReplyError, ReadTimeoutError, SelfSignedError, ServerError, HTTPNotFound, PycurlStreamError, PyCurlRewindError, ProxyResolveError, ProxyError, IllegalURLError, Http2Error, TooManyRedirects, PyCurlEncodingError

# for absurl
from urllib.parse import urlencode, urljoin, urlparse, quote, quote_plus

# for url objects
import inspect
from monseigneur.core.browser import URL

# for cookies and headers
from io import BytesIO, StringIO

# logging
import logging
from monseigneur.core.tools.log import createColoredFormatter

# for extension detection
import mimetypes

# for gzip content encoding
import zlib

# for cookies
from publicsuffixlist import PublicSuffixList
from monseigneur.core.browser.cookies import MonseigneurCookieJar

# for load state and dump state
import pickle
import base64

# for url encoding
from requests.utils import requote_uri

class Request(object):

    method = None
    headers = {}


class Response(object):

    encoding = 'utf-8'

    def __init__(self):
        self.status_code: int = None
        self.content: bytes = None
        self.text: str = None
        self.page = None
        self.headers: dict = None

        self.url: str = None
        self.request: Request = Request()

class CookieJar(MonseigneurCookieJar):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_psl()

    def load_psl(self):
        self.psl = PublicSuffixList()

    def get_cookies(self, domain, parse=False):
        if parse:
            domain = urlparse(domain).netloc
        cookies = super().get_dict(domain=domain)

        wDomain = self.psl.privatesuffix(domain)
        if wDomain:
            wCookies = super().get_dict(domain="." + wDomain)
            dCookies = super().get_dict(domain="." + domain)
            eCookies = super().get_dict(domain="")

            allCookies = {**cookies, **wCookies, **eCookies, **dCookies}

            if not allCookies:
                return ''
            else:
                return '; '.join('%s=%s' % (k, v) for k, v in allCookies.items())
        else:
            return ''

class Session:

    TIMEOUT = 10
    REDIRECTS = 2

    '''
        Browser Session
    '''

    HTTP11 = False
    HTTP2 = False
    HTTP3 = False
    HTTP2_TLS = False
    ACCEPT_ENCODING = False
    VERIFY = True
    CASE_SENSITIVE_HEADERS = False
    CIPHERLIST = ''

    def __init__(self, browser, logger=None, responses_dirname=None, debug=False, delete_logs=True, delete_logs_limit=10000):

        if not logger:
            self.logger = get_task_logger(__name__)
        else:
            self.logger: logging.Logger = logger
        self.debug = debug
        self.cookies = CookieJar()

        self._PROXIES = None
        self.browser = browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36'
        }

        # responses logging
        self.responses_dirname = responses_dirname
        self.responses_count = 1
        self.request_path = None
        self.response = None

        self.first_creation = True
        self.current_state = None

        self._requests = []
        self._responses = []
        self.status_code = None

        self.response_lock = True

        # for logs deletion
        self.DELETE_LOGS = delete_logs
        self.DELETE_LOGS_LIMIT = delete_logs_limit

        # thread id
        self.thread_id = self.get_thread_id()

        c = pycurl.Curl()
        self.c = c

    def get_thread_id(self):
        try:
            from billiard import current_process
            p = current_process()
            if not hasattr(p, 'index'):
                return 0
            return p.index
        except:
            return 0

    def _setup_session(self):
        if self.responses_dirname is None:
            import tempfile
            self.responses_dirname = tempfile.mkdtemp(prefix='monseigneur_session_')
            self.logger.debug('debug data will be saved in this directory: %s' % self.responses_dirname)
        elif not os.path.isdir(self.responses_dirname):
            os.makedirs(self.responses_dirname)

    @property
    def PROXIES(self):
        return self._PROXIES

    @PROXIES.setter
    def PROXIES(self, proxy: dict):
        """
            Example Proxy Dict:

            {
                "host": "zproxy.lum-superproxy.io",
                "port": 22225,
                "username": "lum-customer-c_f9eb8d89-zone-leboncoinnew20000-ip-158.46.169.208",
                "password": "bc37zhm96zj1"
            }
        """
        self._PROXIES = proxy

    def _set_proxy(self, c: pycurl.Curl, proxy: dict):
        if not proxy:
            c.setopt(pycurl.PROXY, '')
            return

        host = proxy.get("host")
        port = proxy.get("port")
        username = proxy.get("username")
        password = proxy.get("password")

        if not any([host, port]):
            raise Exception("Proxy Not Defined")

        c.setopt(pycurl.PROXY, f"http://{host}:{port}")

        if username and password:
            c.setopt(pycurl.PROXYUSERPWD, f"{username}:{password}")
            c.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_BASIC)

    @staticmethod
    def _exception_handler(function):
        try:
            function()
        except pycurl.error as e:
            code, http_error_msg = e.args
            if code == 28:
                cls = PycurlStreamError
                code = 408
            elif code in (92, 18):
                # HTTP/2 stream 15 was not closed cleanly before end of the underlying stream
                cls = PycurlStreamError
            elif code == 65:
                # necessary data rewind wasn't possible
                cls = PyCurlRewindError
            elif code == 5:
                # Could not resolve proxy
                cls = ProxyResolveError
            elif code in (35, 55) or code == (35, 55):
                # OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to www.leboncoin.fr:443
                cls = BrowserSSLError
            elif code == 56:
                # Recv failure: Connection reset by peer
                cls = ConnectionResetByPeer
            elif code == 52:
                cls = EmptyReplyError
            elif code == 3:
                # Illegal characters found in URL
                cls = IllegalURLError
            elif code == 7:
                cls = ProxyError
            elif code == 16:
                cls = Http2Error
            elif code == 60:
                cls = SelfSignedError
            elif code == 61:
                cls = PyCurlEncodingError
            else:
                raise e
            raise cls(code, http_error_msg)

    def _status_code_handler(self, response: Response):
        self.response = response
        http_error_msg = None
        if 400 <= response.status_code < 500:
            http_error_msg = 'Server Error: %s' % (response.status_code)
            cls = ClientError
            if response.status_code == 404:
                cls = HTTPNotFound
        elif 500 <= response.status_code < 600:
            http_error_msg = 'Server Error: %s' % (response.status_code)
            cls = ServerError
        if http_error_msg:
            response.http_error_msg = http_error_msg
            raise cls(response=response)

    def clear_logs_folder(self):
        if self.DELETE_LOGS and (self.responses_count % self.DELETE_LOGS_LIMIT) == 0:
            files = glob.glob('{}/*'.format(self.responses_dirname))
            for file in files:
                os.remove(file)
            self.logger.warning("logs deleted")

    def _debug_function(self, debug_type, debug_msg):
        try:
            if debug_type == 0:
                if self.response_lock and b'Replaced cookie' not in debug_msg:
                    self.response_lock = False
            elif debug_type == 2:
                self._requests += ['\n'.join(x.decode('utf-8') for x in debug_msg.splitlines())]
            elif debug_type == 4:
                self._requests[-1] += "\n%s" % (debug_msg.decode('utf-8').strip())
            elif debug_type == 1:
                decoded_msg = debug_msg.decode('utf-8')
                if 'set-cookie:' in decoded_msg.lower():
                    decoded_msg = decoded_msg.replace('Set-Cookie', 'set-cookie')
                    if 'domain=' in decoded_msg.lower():
                        match = re.match(r'set-cookie: (?P<name>.*?)=(?P<value>.*?);.* (domain|Domain)=(?P<domain>.*?);', decoded_msg)

                        if match:
                            name = match.group('name')
                            value = match.group('value')
                            domain = match.group('domain')

                            self.cookies.set(name=name, value=value, domain=domain)
                    else:
                        match = re.match(r'set-cookie: (?P<name>.*?)=(?P<value>.*?);', decoded_msg)

                        if match:
                            name = match.group('name')
                            value = match.group('value')
                            domain = ""

                            self.cookies.set(name=name, value=value, domain=domain)
                if not self.response_lock:
                    self._responses.append('%s\n' % (decoded_msg.strip()))
                    #self.responses_count += 1
                    self.clear_logs_folder()
                    self.response_lock = True
                else:
                    self._responses[-1] += '%s\n' % (decoded_msg.strip())
        except KeyboardInterrupt:
            os._exit(0)

    def _save_response(self, c: pycurl.Curl, content: BytesIO, response: Response):
        try:
            content_type = c.getinfo(pycurl.CONTENT_TYPE)
            if content_type:
                ext = mimetypes.guess_extension(content_type.split(';')[0]) or ".other"
            else:
                ext = ".other"
        except TypeError:
            ext = ".other"

        for req, res in zip(self._requests, self._responses):

            response.headers = {}

            if not req.startswith("CONNECT"):
                path = re.sub(r'[^A-z0-9\.-_]+', '_', urlparse(response.url).path.rpartition('/')[2])[-10:]
                if path.endswith(ext):
                    ext = ''

                path = '.'.join(re.sub(r'[^A-z0-9\.-_]+', '_', urlparse(response.url).path.rpartition('/')[2])[-10:].split('.')[:-1])

                try:
                    content_type = c.getinfo(pycurl.CONTENT_TYPE)
                    ext = mimetypes.guess_extension(content_type.split(';')[0]) or ".other"
                except (TypeError, AttributeError):
                    ext = ".other"

                response_data_file = '%s-%s_%d-%s%s' % (self.responses_count, response.status_code, self.thread_id, path, ext)

                request_path = os.path.join(self.responses_dirname, response_data_file + '-request.txt')
                response_path = os.path.join(self.responses_dirname, response_data_file + '-response.txt')
                response.file_path = os.path.join(self.responses_dirname, response_data_file)

                self.request_path = request_path

                msg = u'Request saved to %s' % request_path
                self.logger.error(msg)
                msg = u'Response saved to %s' % response_path
                self.logger.info(msg)

                with open(request_path, 'w', encoding='utf-8') as f:
                    f.write(req.strip().replace('\n', '\n\n', 1))
                    f.close()

                response.request.headers = {}
                for l in req.split('\n')[1:]:
                    s = l.split(': ')
                    if len(s) > 1:
                        if len(s) > 2:
                            l = ": ".join([i for i in s if i])

                        k, v = l.split(': ')[0], ': '.join(l.split(': ')[1:])
                        response.request.headers[k] = v

                with open(response_path, 'w', encoding='utf-8') as f:
                    f.write(res.strip().replace('\n', '\n\n', 1))
                    f.close()

                for l in res.split('\n')[1:]:
                    s = l.split(': ')
                    if len(s) > 1:
                        if len(s) > 2:
                            l = ": ".join([i for i in s if i])

                        k, v = l.split(': ')[0], ': '.join(l.split(': ')[1:])
                        response.headers[k.lower()] = v

                self.responses_count += 1

                response_data_path = os.path.join(self.responses_dirname, response_data_file)
                self.response_filepath = response_data_path

            # make response content
            if response.headers.get("content-encoding") == "gzip":
                response.content = self._decode_gzip(content.getvalue())
            else:
                response.content = content.getvalue()

        # make response text
        try:
            text = StringIO(response.content.decode("utf-8"))
        except UnicodeDecodeError:
            text = StringIO(response.content.decode("ISO-8859–1"))

        try:
            response.text = text.getvalue()
        finally:
            text.close()

        import io
        with io.open(response_data_path, 'wb') as f:
            f.write(content.getvalue())
            f.close()

        msg = u'Response data saved to %s' % response_data_path
        self.logger.info(msg)

        return response

    def _decode_gzip(self, content):
        try:
            return zlib.decompress(content, 16 + zlib.MAX_WBITS)
        except:
            return content

    def request(self, method, url, params=None, data=None, headers=None, cookies=None, files=None,
                auth=None, allow_redirects=True, proxies=None,
                verify=None, cert=None, json=None, http_version=None, count_redirs=0):

        original_headers = headers
        self.current_url = url
        if self.first_creation:
            self._setup_session()
            self.first_creation = False

        self._requests = []
        self._responses = []

        content_bytes = BytesIO()
        headers_bytes = BytesIO()

        c = pycurl.Curl()
        self.c = c

        if hasattr(self, "custom_request"):
            self.custom_request()
        c.setopt(pycurl.VERBOSE, self.debug)

        c.setopt(pycurl.DEBUGFUNCTION, self._debug_function)

        # verify to set to True by default
        c.setopt(pycurl.SSL_VERIFYPEER, 1)
        c.setopt(pycurl.SSL_VERIFYHOST, 2)

        # set max redirects allowed
        c.setopt(pycurl.MAXREDIRS, self.REDIRECTS)
        self._set_proxy(c, self._PROXIES)

        if self.ACCEPT_ENCODING == True:
            c.setopt(10102, "")

        try:
            if params:
                url = requote_uri(url) + '?' + urlencode(params).replace('+', '%20')
                c.setopt(pycurl.URL, url)
            else:
                url = requote_uri(url)
                c.setopt(pycurl.URL, url)

            c.setopt(pycurl.FOLLOWLOCATION, False)

            if not verify or self.VERIFY == False:
                c.setopt(pycurl.SSL_VERIFYPEER, 0)
                c.setopt(pycurl.SSL_VERIFYHOST, 0)

            if auth:
                user, pwd = auth

                c.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_BASIC)
                c.setopt(pycurl.USERPWD, "%s:%s" % (user, pwd))
            else:
                c.setopt(pycurl.USERPWD, None)

            if cert:
                c.setopt(pycurl.CAINFO, cert)

            c.setopt(pycurl.TIMEOUT, self.TIMEOUT)

            if self.HTTP2:
                c.setopt(pycurl.HTTP_VERSION, pycurl.CURL_HTTP_VERSION_2_0)

            if self.HTTP2_TLS:
                c.setopt(pycurl.HTTP_VERSION, pycurl.CURL_HTTP_VERSION_2TLS)

            if self.HTTP3:
                c.setopt(pycurl.HTTP_VERSION, 30)

            if http_version and http_version == 1.1:
                c.setopt(pycurl.HTTP_VERSION, pycurl.CURL_HTTP_VERSION_1_1)

            if self.CIPHERLIST:
                c.setopt(pycurl.SSL_CIPHER_LIST, self.CIPHERLIST)

            c.setopt(pycurl.WRITEFUNCTION, content_bytes.write)
            c.setopt(pycurl.HEADERFUNCTION, headers_bytes.write)

            if json and ('content-type' not in map(str.lower, self.headers.keys()) or \
                    'content-type' not in map(str.lower, headers.keys())):
                headers['content-type'] = 'application/json; charset=utf-8'

            if json:
                fields = pjson.dumps(json, ensure_ascii=True)
                c.setopt(pycurl.POSTFIELDS, fields)
            elif data:
                fields = urlencode(data, safe='', quote_via=quote)
                c.setopt(pycurl.POSTFIELDS, fields)

            # here are the get, post, put, head methods
            c.setopt(pycurl.CUSTOMREQUEST, method or 'GET')

            # patch head, set nobody to True
            if method == 'HEAD':
                c.setopt(pycurl.NOBODY, 1)

            temp_headers = self.headers.copy()
            temp_headers = dict((k.lower(), v) for k, v in temp_headers.items())
            if headers:
                for k, v in headers.items():
                    temp_headers[k.lower()] = v

            c.setopt(pycurl.SSLVERSION, 393216)
            cookielist = self.cookies.get_cookies(domain=url, parse=True)


            if cookies:
                cookies = '; '.join(f'{k}={v}' for k, v in cookies.items())
                cookielist += cookies

            if cookielist:
                c.setopt(pycurl.COOKIE, cookielist)

            headers = [f'{k}: {v}' for k, v in temp_headers.items()]
            if self.CASE_SENSITIVE_HEADERS:
                for i, header in enumerate(headers.copy()):
                    name, value = header.split(': ')
                    name = '-'.join([w.capitalize() for w in name.split('-')])
                    headers[i] = f'{name}: {value}'
            # fix encoding
            headers = [h.encode('utf-8') for h in headers]
            c.setopt(pycurl.HTTPHEADER, headers)

            Session._exception_handler(c.perform)

            response = Response()
            response.status_code = c.getinfo(pycurl.RESPONSE_CODE)
            response.url = c.getinfo(pycurl.EFFECTIVE_URL)
            response.request.method = method

            # our decoding logic
            # also sets response text & content & headers
            response = self._save_response(c, content_bytes, response)
            self.response = response

            headers_bytes.seek(0)

            self.status_code = response.status_code
            self._status_code_handler(response)

            if allow_redirects:
                if count_redirs > 5:
                    raise TooManyRedirects
                if response.status_code == 301 or response.status_code == 302 or response.status_code == 307 or response.status_code == 308:
                    return self.request('GET', c.getinfo(pycurl.REDIRECT_URL), headers=original_headers, count_redirs=count_redirs+1)
        finally:
            content_bytes.close()
            headers_bytes.close()

        return response

    def close(self):
        self.c.close()

class PyCurlBrowser(object):

    TIMEOUT = 10
    DOWNGRADE = False
    DEBUG = True
    VERIFY = True
    HTTP11 = False
    HTTP2 = False
    HTTP2_TLS = False
    HTTP3 = False
    CIPHERLIST = None
    ACCEPT_ENCODING = None
    CASE_SENSITIVE_HEADERS = False
    CIPHERLIST = ''

    _urls = None

    _DELETE_LOGS = True
    """
    Deletes logs after requests go over a certain number
    """

    _DELETE_LOGS_LIMIT = 10000
    """
    Clear folder after x amount of requests
    """

    def __init__(self, logger=None, responses_dirname=None, **kwargs):

        if logger is None:
            self.logger = logging.getLogger('browser')
            formatter = '%(asctime)s:%(levelname)s:%(name)s:%(filename)s:%(lineno)d:%(funcName)s %(message)s'
            sh = logging.StreamHandler(sys.stdout)
            #sh.setLevel(logging.DEBUG)
            sh.setFormatter(createColoredFormatter(sys.stdout, formatter))
            self.logger.addHandler(sh)
            self.logger.propagate = False
            self.logger.settings = {"ssl_insecure": True}
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger = logger

        """
        def handle_ctrl_c(signal, frame):
            print("Got ctrl+c, going down!")
            sys.exit(0)
        signal.signal(signal.SIGINT, handle_ctrl_c)
        """

        attrs = [(name, func) for (name, func) in inspect.getmembers(self) if type(func) == URL]
        attrs.sort(key=lambda v: v[1]._creation_counter)
        self._urls = OrderedDict(deepcopy(attrs))

        for k, v in self._urls.items():
            setattr(self, k, v)
        for url in self._urls.values():
            url.browser = self

        self._responses_dirname = responses_dirname

        self.session = Session(
            browser=self,
            logger=self.logger,
            responses_dirname=self._responses_dirname
        )
        self.session.debug = self.DEBUG
        self.session.VERIFY = self.VERIFY
        self.session.ACCEPT_ENCODING = self.ACCEPT_ENCODING
        self.session.TIMEOUT = self.TIMEOUT
        self.session.HTTP2  = self.HTTP2
        self.session.HTTP2_TLS  = self.HTTP2_TLS
        self.session.HTTP3  = self.HTTP3
        self.session.HTTP11 = self.HTTP11
        self.session.CIPHERLIST = self.CIPHERLIST
        self.status_code = self.session.status_code
        self.session.CASE_SENSITIVE_HEADERS = self.CASE_SENSITIVE_HEADERS

        # for those url objects
        self.page = None
        self.url = None
        self.current_url = None
        self.response: Response = None

        self.delete_logs = kwargs.pop('delete_logs', True)
        self.delete_logs_limit = kwargs.pop('delete_logs_limit', 10000)

    @property
    def PROXIES(self):
        return self.session.PROXIES

    @PROXIES.setter
    def PROXIES(self, value):
        self.session.PROXIES = value

    @property
    def responses_count(self):
        return self.session.responses_count

    @property
    def responses_dirname(self):
        return self._responses_dirname

    @responses_dirname.setter
    def responses_dirname(self, path):
        self._responses_dirname = path
        if path and not os.path.isdir(path):
            try:
                os.makedirs(path)
            except FileExistsError:
                # probably created by another thread at the same time
                pass
        self.session.responses_dirname = path

    @property
    def DELETE_LOGS(self):
        return self._DELETE_LOGS

    @property
    def DELETE_LOGS_LIMIT(self):
        return self._DELETE_LOGS_LIMIT

    @DELETE_LOGS.setter
    def DELETE_LOGS(self, value):
        self.session.DELETE_LOGS = value

    @DELETE_LOGS_LIMIT.setter
    def DELETE_LOGS_LIMIT(self, value):
        self.session.DELETE_LOGS_LIMIT = value

    def absurl(self, uri, base=None):
        if not base:
            base = self.url
        if base is None or base is True:
            base = self.BASEURL
        return urljoin(base, uri)

    def deinit(self):
        self.session.close()

    def url_handle(self, response):
        response.page = None

        for url in self._urls.values():

            response.page = url.handle(response)
            if response.page is not None:
                self.logger.info('Handle %s with %s', response.url, response.page.__class__.__name__)
                break

        if response.page is None:
            regexp = r'^(?P<proto>\w+)://.*'
            if self.DOWNGRADE:
                proto_response = re.match(regexp, response.url)
                if proto_response:
                    proto_response = proto_response.group('proto')
                    proto_base = re.match(regexp, self.BASEURL).group('proto')

                    if proto_base == 'https' and proto_response != 'https':
                        raise BrowserHTTPSDowngrade()

            self.logger.warning('Unable to handle %s', response.url)

        self.page = response.page

    def location(self, url, method='GET', headers={}, cookies=None, params=None, data=None, json=None, verify=True, auth=None, cert=None, allow_redirects=True, http_version=None, **kwargs):
        if self.page is not None:
            # Call leave hook.
            self.page.on_leave()
        response = self.session.request(method, url, params=params, headers=headers, cookies=cookies, data=data, json=json, verify=verify, auth=auth, allow_redirects=allow_redirects, cert=cert, http_version=http_version)
        self.response = response
        self.url = response.url

        self.url_handle(response)

        self.page = response.page
        if self.page is not None:
            # Call load hook.
            self.page.on_load()

        return response


class PyCurlLogin(PyCurlBrowser):

    def __init__(self, username, password, logger, responses_dirname, **kwargs):
        super().__init__(logger=logger, responses_dirname=responses_dirname, **kwargs)
        self.username = username
        self.password = password

    def do_login(self):
        """
        Abstract method to implement to login on website.

        It is called when a login is needed.
        """
        raise NotImplementedError()

    def do_logout(self):
        """
        Logout from website.

        By default, simply clears the cookies.
        """
        self.session.cookies.clear()

class PyCurlMixin(object):
    __states__ = ()

    def load_state(self, state):
        if 'cookies' in state:
            try:
                self.session.cookies = pickle.loads(zlib.decompress(base64.b64decode(state['cookies'])))
                if not isinstance(self.session.cookies, CookieJar):
                    self.session.cookies.__class__ = CookieJar
                    self.session.cookies.load_psl()
            except (TypeError, zlib.error, EOFError, ValueError):
                self.session.cookies = CookieJar()
                self.logger.error('unable to reload cookies from storage')
            else:
                self.logger.info('reloaded cookies from storage')
        for attrname in self.__states__:
            if attrname in state:
                setattr(self, attrname, state[attrname])

        if state.get('url', None):
            self.location(state.get('url'))

    def dump_state(self):
        state = {}
        if hasattr(self, 'page') and self.page:
            state['url'] = self.page.url
        state['cookies'] = base64.b64encode(zlib.compress(pickle.dumps(self.session.cookies, -1))).decode("utf8")
        for s in self.__states__:
            state[s] = getattr(self, s, None)
        self.logger.info('stored cookies into storage')
        return state
