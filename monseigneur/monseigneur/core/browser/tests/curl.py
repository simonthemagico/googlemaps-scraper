import pickle
from monseigneur.core.browser import URL
from monseigneur.core.browser.curl import PyCurlBrowser, PyCurlMixin

from pages import HomePage, ResultsPage, PostPage, IpifyPage, GooglePage, StreamlitPage, RedirectIssuePage

class AnyBrowser(PyCurlBrowser):

    BASEURL = "http://195.154.26.212:8002"
    DEBUG = True
    TIMEOUT = 40
    
    me_page = URL(r"/v1/me", HomePage)
    run_results_page = URL(r"/v1/results", ResultsPage)
    run_results_page = URL(r"/v1/results", ResultsPage)
    http_bin_post_page = URL(r"https://httpbingo.org/post", PostPage)
    ipify_page = URL(r"https://api.ipify.org\?format=json", IpifyPage)
    http_bin_html_page = URL(r"https://httpbingo.org/html", PostPage)
    google_page = URL(r"https://www.google.com/", GooglePage)
    streamlit_page = URL(r"http://195.154.26.212:8500/", StreamlitPage)
    products_page = URL(r'https://allegro.pl/kategoria/(.*)', RedirectIssuePage)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.session.headers.update({
            'Authorization': 'Token b192300d9033664966b90090adc49e41c0c58366'
        })

    def get_me(self):
        self.me_page.go()
        assert self.me_page.is_here()

        first_name = self.page.get_first_name()
        assert first_name == 'Simon'

    def get_run_results(self):
        self.run_results_page.go(method='GET', json={
            "run": "7f1c290f1cabb751e5f4b2a0f957c1c3"
        })
        assert self.run_results_page.is_here()
        doc = self.page.get_doc()
        assert doc.get('next') == 'http://195.154.26.212:8002/v1/results?page=2'

    def test_http_post_normal_data(self):
        self.http_bin_post_page.go(method='POST', data={
            'first_name': 'anon'
        })
        assert self.http_bin_post_page.is_here()
        doc = self.page.get_json()
        assert doc["form"] == {"first_name": ["anon"]}

    def test_http_post_json_data(self):
        self.responses_dirname = "hello"
        self.http_bin_post_page.go(method='POST', json={
            'first_name': 'anon'
        }, headers={
            'something': 'not right 1'
        })
        assert self.http_bin_post_page.is_here()
        doc = self.page.get_json()
        assert doc["json"] == {"first_name": "anon"}

    def test_http_put(self):
        self.me_page.go(method='PUT', data={"first_name": "Simon"})
        assert self.me_page.is_here()

        first_name = self.page.get_first_name()
        assert first_name == 'Simon'

    def test_proxy(self):
        self.session.PROXIES = {
            "host": "zproxy.lum-superproxy.io",
            "port": 22225,
            "username": "lum-customer-c_f9eb8d89-zone-leboncoinnew20000-ip-158.46.169.208",
            "password": "bc37zhm96zj1"
        }

        self.ipify_page.go()
        assert self.ipify_page.is_here()

        doc = self.page.get_doc()
        assert doc.get('ip') == '158.46.169.208'

    def test_non_proxy(self):
        self.session.PROXIES = {}
        self.ipify_page.go()
        assert self.ipify_page.is_here()

        doc = self.page.get_doc()
        assert not doc.get('ip') == '158.46.169.208'

    def test_timeout_error(self):
        self.session.TIMEOUT = 1
        self.session._setup_session()

        self.test_proxy()

    # head method throws AssertionError in is_here()
    def test_head_method(self):
        self.http_bin_html_page.go(method='HEAD')
        assert not self.http_bin_html_page.is_here()

    def test_redirect_saving(self):
        self.google_page.go()

    def test_auth(self):
        k = self.location("http://195.154.26.212:8500/", auth=('matrix', 'AltiuS20102010!!?'))
        assert k.status_code == 200

    def test_content_encoding_gzip(self):
        self.google_page.go()

    def test_content_encoding_br(self):
        r = self.location("https://www.edureka.co/community/77315/unicodedecodeerror-codec-decode-position-invalid-start-byte")
        print(r.headers)

    def test_cookies(self):
        self.session.cookies.update({
            'something': 'weird'
        })
        self.http_bin_post_page.go(method='POST', data={
            'first_name': 'anon'
        })
        assert self.http_bin_post_page.is_here()
        assert self.page.get_cookies() == 'something=weird'

        self.location("https://www.accuweather.com/")
        self.location("https://www.accuweather.com/", cookies={
            "hey": "hello"
        })

    def test_cookies_persistent(self):
        self.location("https://www.google.com")
        print(self.session.cookies)
        print(self.session.cookies.get_dict())
        self.location("https://www.google.com/")

    def test_redirect(self):
        self.location("https://allegro.pl/kategoria/drukarki-i-skanery-urzadzenia-wielofunkcyjne-260347?p=2")

    def test_redirect_301(self):
        self.location("https://loom.com/share/ecf29d323d114a62a2ecd709964d7814&page=1", allow_redirects=True)

    def test_angolia(self):
        self.session.PROXIES = {
            "host": "smartbalance2.com",
            "port": 40394,
            "username": "user-sp0e9f6467-sessionduration-30",
            "password": "altius2010"
        }
        headers = {
            'x-algolia-application-id': 'KAR1UEUPJD',
            'content-type': 'application/x-www-form-urlencoded',
            'x-algolia-api-key': 'ZDE4YmFmNjYxZDliYzA3ZmZiZGJkNWRjMDZkZTJhODY1ODkwOGNlODkwZTYwYTQwZDE4NTI4MmY2ZDczNTFhYXZhbGlkVW50aWw9MTYzNzA3NzEwNCZyZXN0cmljdEluZGljZXM9YXVjdGlvbnMlMkNwcm9kX2F1Y3Rpb25zJTJDcHJvZF9hdWN0aW9uc18qJTJDbG90cyUyQ3Byb2RfbG90cyUyQ3Byb2RfbG90c18qJTJDcHJvZF9sb3RzX2xvdE5yX2FzYyUyQ3Byb2RfbG90c19sb3ROcl9kZXNjJTJDcHJvZF9sb3RzX2F1Y3Rpb25EYXRlX2FzYyUyQ3Byb2RfbG90c19hdWN0aW9uRGF0ZV9kZXNjJTJDcHJvZF91cGNvbWluZ19sb3RzX2FzYyUyQ3Byb2RfdXBjb21pbmdfbG90c19kZXNjJTJDcHJvZF9sb3RzX2xvd0VzdGltYXRlX2FzYyUyQ3Byb2RfbG90c19sb3dFc3RpbWF0ZV9kZXNjJTJDcHJvZF9zdWdnZXN0ZWRfbG90cyUyQ3Byb2R1Y3RfaXRlbXMlMkNwcm9kX3Byb2R1Y3RfaXRlbXMlMkNwcm9kX3Byb2R1Y3RfaXRlbXNfKiUyQ3Byb2RfcHJvZHVjdF9pdGVtc19sb3dFc3RpbWF0ZV9hc2MlMkNwcm9kX3Byb2R1Y3RfaXRlbXNfbG93RXN0aW1hdGVfZGVzYyUyQ3Byb2RfcHJvZHVjdF9pdGVtc19wdWJsaXNoRGF0ZV9kZXNjJTJDc290aGVieXNfY2F0ZWdvcmllcyUyQ3NvdGhlYnlzX2NhdGVnb3JpZXMlMkNzb3RoZWJ5c19jYXRlZ29yaWVzXyolMkN0YWdnaW5nX3RhZ3NldHMlMkNwcm9kX3RhZ2dpbmdfdGFnc2V0cyUyQ3Byb2RfdGFnZ2luZ190YWdzZXRzXyolMkN0YWdnaW5nX3RhZ3MlMkNwcm9kX3RhZ2dpbmdfdGFncyUyQ3Byb2RfdGFnZ2luZ190YWdzXyolMkNvbmJvYXJkaW5nX3RvcGljcyUyQ3Byb2Rfb25ib2FyZGluZ190b3BpY3MlMkNwcm9kX29uYm9hcmRpbmdfdG9waWNzXyolMkNmb2xsb3dhYmxlX3RvcGljcyUyQ3Byb2RfZm9sbG93YWJsZV90b3BpY3MlMkNwcm9kX2ZvbGxvd2FibGVfdG9waWNzXyomZmlsdGVycz1OT1Qrc3RhdGUlM0FDcmVhdGVkK0FORCtOT1Qrc3RhdGUlM0FEcmFmdCtBTkQrTk9UK2lzVGVzdFJlY29yZCUzRDErQU5EK05PVCtsb3RTdGF0ZSUzQUNyZWF0ZWQrQU5EK05PVCtsb3RTdGF0ZSUzQURyYWZ0K0FORCslMjhOT1QraXNIaWRkZW4lM0F0cnVlK09SK2xlYWRlcklkJTNBMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwJTI5'
        }
        params = {
            'x-algolia-agent': 'Algolia for JavaScript (4.8.3); Browser'
        }
        data = {"query": "", "filters": "auctionId: 4b964150-2bc9-40f5-ade9-e51b93e0104e AND objectTypes:\"All\"", "facetFilters": [["lotState:Closed"], ["withdrawn:false"]], "hitsPerPage": 48, "page": "1", "facets": ["*"], "numericFilters": []}
        self.location('https://kar1ueupjd-1.algolianet.com/1/indexes/prod_lots/query', method='POST', json=data, params=params, headers=headers)
        self.location('https://www.sothebys.com/en/buy/auction/2019/diamonds-online-3/de26d6ef-6406-4b0a-aff2-e035d2fa0be8')

class AnyStatesMixin(PyCurlBrowser, PyCurlMixin):

    BASEURL = "https://www.google.com"
    
    google_page = URL(r"/", GooglePage)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def go_google(self):
        self.google_page.go()
        
        with open("state.pickle", "wb") as f:
            pickle.dump(self.dump_state(), f)
            f.close()

        print(self.session.cookies)

    def go_google_back(self):
        import json

        print(self.session.cookies)
        k = self.location('http://localhost:8100/state/054e20fec23a05156370bb9d996ee256', auth=('dropsync', '!nSlEtbR0Tlo'))
        z = json.loads(k.text)
        self.load_state(z)
        print(self.session.cookies)

        # with open("state.pickle", "rb") as f:
        #     state = pickle.load(f)
        #     self.load_state(state)

        # print(self.session.cookies)
        # self.google_page.go()

if __name__ == "__main__":
    b = AnyBrowser(responses_dirname='test')
    # b.test_cookies_persistent()
    b.test_http_post_normal_data()
    b.test_http_post_json_data()
    # b.test_redirect_301()
    # b.test_angolia()
    # b.test_proxy()

    # b = AnyStatesMixin(responses_dirname="test")
    # b.go_google()
    # b.go_google_back()