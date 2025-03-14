from curl_cffi import requests, CurlOpt, Curl
from curl_cffi._wrapper import ffi, lib
from monseigneur.core.browser.browsers import PagesBrowser
import requests as original_requests
from collections import defaultdict
from urllib.parse import urlparse
import json
import os
import re
import sys
import mimetypes
import uuid
import logging
import threading

local = threading.local()

logging.basicConfig(level=logging.DEBUG)

CURL_HTTP_VERSION_1_1 = 2
CURL_HTTP_VERSION_2TLS = 4


@ffi.def_extern()
def debug_function(curl, type: int, data, size, clientp) -> int:
    try:
        text = ffi.buffer(data, size)[:]
        if not hasattr(local, "DEBUG_DATA"):
            local.DEBUG_DATA = {'request': [], 'response': []}

        if type == 0:
            try:
                decoded_text = text.decode().strip()
            except UnicodeDecodeError:
                decoded_text = text.decode('latin-1').strip()
            if decoded_text.startswith('Cipher'):
                local.DEBUG_DATA['request'].append(decoded_text + '\n')
        elif type == 2:
            local.DEBUG_DATA['request'].append(text.decode())
        elif type == 1:
            local.DEBUG_DATA['response'].append(text.decode().strip())
        return 0
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected in debug_function. Stopping the program.")
        os._exit(0)  # Forcefully stop the program


class CustomCurlSession(requests.Session):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # hooks property
        # session.hooks['response'].append(self.get_destination_ip)
        self.hooks = defaultdict(list)
        self.quote = ""

    def mount(self, *args, **kwargs):
        pass

    def prepare_request(self, req):
        return req

    def make_request_body(self, request):
        if request.data:
            return "&".join(["{k}={v}".format(k=k, v=v) for k, v in request.data.items()])
        elif request.json:
            return json.dumps(request.json)
        elif request.files:
            return request.files
        else:
            return None

    def _set_curl_options(self, curl, method, url, *args, **kwargs):
        kwargs["headers"] = {k.lower(): v for k, v in (kwargs.get("headers", {}) or {}).items()}
        args = super()._set_curl_options(curl, method, url, *args, **kwargs)

        # if url startswith with http://localhost
        # set to http1.1
        if url.startswith("http://localhost"):
            curl.setopt(CurlOpt.HTTP_VERSION, CURL_HTTP_VERSION_1_1)

        return args

    def request(self, *args, **kwargs):
        curl = Curl(debug=True)
        lib._curl_easy_setopt(curl._curl, CurlOpt.DEBUGFUNCTION, lib.debug_function)
        self._curl = curl
        self._local.curl = curl
        return super().request(*args, **kwargs)

    def send(self, *args, **kwargs):
        (preq, ) = args
        preq: original_requests.Request

        # not supported options
        kwargs.pop("stream", None)
        callback = kwargs.pop("callback", lambda _, x: x)
        kwargs.pop("is_async", None)

        response = self.request(
            method=preq.method,
            url=preq.url,
            headers=preq.headers,
            files=preq.files,
            data=preq.data or None,
            json=preq.json,
            params=preq.params,
            auth=preq.auth,
            cookies=preq.cookies or {},
            quote=self.quote,
            **kwargs
        )

        self.response = response

        # set request
        preq.body = self.make_request_body(preq)
        response.request = preq

        # run hooks
        for hook in self.hooks['response']:
            hook(response=response, **kwargs)

        return callback("", response)

class CurlCffiBrowser(PagesBrowser):

    IMPERSONATE = "safari15_5"
    QUOTE = ""

    def __init__(self, *args, **kwargs):
        self.session = self._create_session()
        super().__init__(*args, **kwargs)

    def get_destination_ip(self, response, **kwargs):
        self.logger.debug("socket is:")
        socket = response.request.__dict__
        self.logger.debug(socket)
        socket = None

    def save_response(self, response, warning=False, **kwargs):
        # Ensure thread-local storage for DEBUG_DATA
        if not hasattr(local, "DEBUG_DATA"):
            local.DEBUG_DATA = {'request': [], 'response': []}

        if self.save_logs is not False:
            if self.responses_dirname is None:
                self.config_path = os.getenv("MONSEIGNEUR_CONFIG_PATH") or os.path.join(os.environ['HOME'], "mdev/monseigneur/mbackend/")
                with open(os.path.join(self.config_path, 'config.json')) as json_data_file:
                    self.config = json.load(json_data_file)
                if self.backend_name is None:
                    self.backend_name = 'conn_%s_' % uuid.uuid4().hex
                self.responses_dirname = os.path.join(os.environ['HOME'], self.config["saved_responses_config"]["responses_path"][0], self.backend_name)
                if not os.path.isdir(self.responses_dirname):
                    os.makedirs(self.responses_dirname)
                self.logger.info('Debug data will be saved in this directory: %s' % self.responses_dirname)
        else:
            self.logger.info('Not saving logs (self.save_logs)')
            return

        # Get the content-type and handle extensions
        mimetype = response.headers.get('Content-Type', '').split(';')[0]
        if mimetype == 'text/plain':
            ext = '.txt'
        else:
            ext = mimetypes.guess_extension(mimetype, False) or ''

        with self.responses_count_lock:
            counter = self.responses_count
            self.responses_count += 1

        path = re.sub(r'[^A-z0-9\.-_]+', '_', urlparse(str(response.url)).path.rpartition('/')[2])[-10:]
        if path.endswith(ext):
            ext = ''

        filename = '%02d-%d%s%s%s' % (counter, response.status_code, '-' if path else '', path, ext)

        response_filepath = os.path.join(self.responses_dirname, filename)
        self.response_filepath = response_filepath

        request = response.request
        self.response = response
        with open(response_filepath + '-request.txt', 'w', encoding='utf-8') as f:
            for header in local.DEBUG_DATA['request']:
                f.write('%s\n' % header)
            if hasattr(request, 'body') and request.body is not None:  # separate '' from None
                f.write('%s' % request.body)

        with open(response_filepath + '-response.txt', 'w', encoding='utf-8') as f:
            if hasattr(response, 'elapsed'):
                f.write('Time: %3.3fs\n\n' % response.elapsed)
            for header in local.DEBUG_DATA['response']:
                f.write('%s\n' % header)

        with open(response_filepath, 'wb') as f:
            f.write(response.content)

        match_filepath = os.path.join(self.responses_dirname, 'url_response_match.txt')
        with open(match_filepath, 'a', encoding='utf-8') as f:
            f.write('# %d %s %s\n' % (response.status_code, response.reason, response.headers.get('Content-Type', '')))
            f.write('%s\t%s\n' % (response.url, filename))

        msg = u'Response saved to %s' % response_filepath
        if warning:
            self.logger.warning(msg)
        else:
            self.logger.info(msg)

        # Reset debug data
        local.DEBUG_DATA['request'] = []
        local.DEBUG_DATA['response'] = []

        # Clear logs folder
        self.clear_logs_folder()

    @property
    def PROXIES(self):
        return self.session.proxies

    @PROXIES.setter
    def PROXIES(self, value):
        self.session.proxies = value

    @PROXIES.deleter
    def PROXIES(self):
        self.session.proxies = {}

    def _create_session(self) -> CustomCurlSession:
        curl = Curl(debug=True)
        lib._curl_easy_setopt(curl._curl, CurlOpt.DEBUGFUNCTION, lib.debug_function)
        return CustomCurlSession(curl=curl)

    def _setup_session(self, profile):
        super()._setup_session(profile)

        self.session: CustomCurlSession

        # set cookies
        self.session.cookies = requests.cookies.Cookies()

        # set impersonate
        self.session.impersonate = self.IMPERSONATE

        # set quote
        self.session.quote = self.QUOTE

        # no default headers
        self.session.headers = {}

        # set timeout
        self.session.timeout = self.TIMEOUT

if __name__ == "__main__":
    browser = CurlCffiBrowser(
        responses_dirname="test"
    )
    browser.location("https://www.google.com", method="GET")
    from requests.cookies import cookiejar_from_dict
    print(browser.session.cookies.jar)
    print(cookiejar_from_dict(browser.session.cookies))
