# -*- coding: utf-8 -*-

__all__ = ['Javascript']


from monseigneur.core.tools.log import getLogger


class Javascript(object):
    HEADER = """
    function btoa(str) {
        var buffer;

        if (str instanceof Buffer) {
            buffer = str;
        } else {
            buffer = new Buffer(str.toString(), 'binary');
        }

        return buffer.toString('base64');
    }

    function atob(str) {
        return new Buffer(str, 'base64').toString('binary');
    }

    document = {
        createAttribute: null,
        styleSheets: null,
        characterSet: "UTF-8",
        documentElement: {}
    };

    history = {};

    screen = {
        width: 1280,
        height: 800
    };

    var XMLHttpRequest = function() {};
    XMLHttpRequest.prototype.onreadystatechange = function(){};
    XMLHttpRequest.prototype.open = function(){};
    XMLHttpRequest.prototype.setRequestHeader = function(){};
    XMLHttpRequest.prototype.send = function(){};

    /* JS code checks that some PhantomJS globals aren't defined on the
    * global window object; put an empty window object, so that all these
    * tests fail.
    * It then tests the user agent against some known scrappers; just put
    * the default Tor user agent in there.
    */
    window = {
        document: document,
        history: history,
        screen: screen,
        XMLHttpRequest: XMLHttpRequest,

        innerWidth: 1280,
        innerHeight: 800,

        close: function(){}
    };

    navigator = {
        userAgent: "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0",
        appName: "Netscape"
    };
    """

    def __init__(self, script, logger=None, domain=""):
        try:
            import execjs
        except ImportError:
            raise ImportError('Please install PyExecJS')

        self.runner = execjs.get()
        self.logger = getLogger('js', logger)

        window_emulator = self.HEADER

        if domain:
            window_emulator += "document.domain = '" + domain + "';"
            window_emulator += """
            if (typeof(location) === "undefined") {
                var location = window.location = {
                    host: document.domain
                };
            }
            """

        self.ctx = self.runner.compile(window_emulator + script)

    def call(self, *args, **kwargs):
        retval = self.ctx.call(*args, **kwargs)

        self.logger.debug('Calling %s%s = %s', args[0], args[1:], retval)

        return retval
