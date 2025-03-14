from monseigneur.core.browser.pages import HTMLPage, JsonPage
from monseigneur.core.browser.filters.json import Dict

import json

class HomePage(JsonPage):

    def get_first_name(self):
        return Dict("first_name")(self.doc)

class ResultsPage(JsonPage):

    def get_doc(self):
        return self.doc

class PostPage(HTMLPage):

    def get_doc(self):
        return '\n'.join(self.doc.xpath("//html//text()"))

    def get_json(self):
        doc = json.loads(self.get_doc())
        return doc

    def get_cookies(self):
        doc = json.loads(self.get_doc())
        return Dict("headers/Cookie")(doc)

class IpifyPage(JsonPage):

    def get_doc(self):
        return self.doc

class GooglePage(HTMLPage):
    
    def get_doc(self):
        return self.doc

class StreamlitPage(HTMLPage):

    def get_doc(self):
        return self.doc

class RedirectIssuePage(HTMLPage):
    pass