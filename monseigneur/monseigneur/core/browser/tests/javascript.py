from monseigneur.core.browser import URL
from monseigneur.core.browser.javascript import PlaywrightBrowser
from monseigneur.core.browser.pages import HTMLPage

import pickle

class GooglePage(HTMLPage):

    def on_load(self):
        self.browser.wait_for_selector("xpath=//div[text()=\"J'accepte\"]")
        self.browser.click('xpath=//div[text()="J\'accepte"]')

class Browser(PlaywrightBrowser):

    DRIVER = 'webkit'
    HEADLESS = False
    BASEURL = 'https://www.google.com'

    google_page = URL(r'/$', GooglePage)
    
    def go_google(self):
        self.google_page.go()

if __name__=="__main__":
    b = Browser()
    b.go_google()