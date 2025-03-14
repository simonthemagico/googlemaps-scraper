# -*- coding: utf-8 -*-

class BrowserIncorrectPassword(Exception):
    pass


class BrowserForbidden(Exception):
    pass


class BrowserBanned(BrowserIncorrectPassword):
    pass


class BrowserUnavailable(Exception):
    pass


class BrowserInteraction(Exception):
    pass


class BrowserQuestion(BrowserInteraction):
    """
    When raised by a browser,
    """
    def __init__(self, *fields):
        self.fields = fields


class BrowserRedirect(BrowserInteraction):
    def __init__(self, url):
        self.url = url

    def __str__(self):
        return 'Redirecting to %s' % self.url


class CaptchaQuestion(Exception):
    """Site requires solving a CAPTCHA (base class)"""
    # could be improved to pass the name of the backendconfig key

    def __init__(self, type=None, **kwargs):
        super(CaptchaQuestion, self).__init__("The site requires solving a captcha")
        self.type = type
        for key, value in kwargs.items():
            setattr(self, key, value)


class ImageCaptchaQuestion(CaptchaQuestion):
    type = 'image_captcha'

    image_data = None

    def __init__(self, image_data):
        super(ImageCaptchaQuestion, self).__init__(self.type, image_data=image_data)


class NocaptchaQuestion(CaptchaQuestion):
    type = 'g_recaptcha'

    website_key = None
    website_url = None

    def __init__(self, website_key, website_url):
        super(NocaptchaQuestion, self).__init__(self.type, website_key=website_key, website_url=website_url)


class RecaptchaQuestion(CaptchaQuestion):
    type = 'g_recaptcha'

    website_key = None
    website_url = None

    def __init__(self, website_key, website_url):
        super(RecaptchaQuestion, self).__init__(self.type, website_key=website_key, website_url=website_url)


class FuncaptchaQuestion(CaptchaQuestion):
    type = 'funcaptcha'

    website_key = None
    website_url = None
    sub_domain = None

    def __init__(self, website_key, website_url, sub_domain=None):
        super(FuncaptchaQuestion, self).__init__(
            self.type, website_key=website_key, website_url=website_url, sub_domain=sub_domain)


class BrowserHTTPNotFound(BrowserUnavailable):
    pass


class BrowserHTTPError(BrowserUnavailable):
    pass


class BrowserHTTPSDowngrade(BrowserUnavailable):
    pass


class BrowserSSLError(BrowserUnavailable):
    pass


class ConnectionResetByPeer(BrowserUnavailable):
    pass


class ParseError(Exception):
    pass


class FormFieldConversionWarning(UserWarning):
    """
    A value has been set to a form's field and has been implicitly converted.
    """


class NoAccountsException(Exception):
    pass


class ModuleInstallError(Exception):
    pass


class ModuleLoadError(Exception):
    def __init__(self, module_name, msg):
        super(ModuleLoadError, self).__init__(msg)
        self.module = module_name


class ActionNeeded(Exception):
    pass


class AuthMethodNotImplemented(ActionNeeded):
    pass


class BrowserPasswordExpired(ActionNeeded):
    pass


class NeedLogin(Exception):
    pass


class NoItemFound(Exception):
    pass


class Http2Error(Exception):
    pass
