import unittest
from monseigneur.core.browser.curl_impersonate import CurlImpersonateBrowser

class TestBrowser(unittest.TestCase):

    def setUp(self) -> None:
        self.browser = CurlImpersonateBrowser()

    def test_google(self):
        self.browser.location(url='https://www.google.com')
        self.browser.location(url='https://www.google.com')