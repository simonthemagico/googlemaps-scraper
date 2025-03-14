# -*- coding: utf-8 -*-

import lxml.html as html
from six.moves.html_parser import HTMLParser

from monseigneur.monseigneur.core.tools.compat import basestring, unicode, urljoin
from monseigneur.monseigneur.core.tools.html import html2text

from .base import _NO_DEFAULT, Filter, FilterError, _Selector, debug, ItemNotFound
from .standard import (
    TableCell, ColumnNotFound, # TODO move class here when modules are migrated
    CleanText,
)

__all__ = ['CSS', 'XPath', 'XPathNotFound', 'AttributeNotFound',
           'Attr', 'Link', 'AbsoluteLink',
           'CleanHTML', 'FormValue', 'HasElement',
           'TableCell', 'ColumnNotFound',
           'ReplaceEntities',
          ]


class XPathNotFound(ItemNotFound):
    pass


class AttributeNotFound(ItemNotFound):
    pass


class CSS(_Selector):
    """Select HTML elements with a CSS selector

    For example::

        obj_foo = CleanText(CSS('div.main'))

    will take the text of all ``<div>`` having CSS class "main".
    """
    def select(self, selector, item):
        ret = item.cssselect(selector)
        if isinstance(ret, list):
            for el in ret:
                if isinstance(el, html.HtmlElement):
                    self.highlight_el(el, item)

        return ret


class XPath(_Selector):
    """Select HTML elements with a XPath selector
    """
    pass


class Attr(Filter):
    """Get the text value of an HTML attribute.

    Get value from attribute `attr` of HTML element matched by `selector`.

    For example::

        obj_foo = Attr('//img[@id="thumbnail"]', 'src')

    will take the "src" attribute of ``<img>`` whose "id" is "thumbnail".
    """

    def __init__(self, selector, attr, default=_NO_DEFAULT):
        """
        :param selector: selector targeting the element
        :param attr: name of the attribute to take
        """

        super(Attr, self).__init__(selector, default=default)
        self.attr = attr

    @debug()
    def filter(self, el):
        """
        :raises: :class:`XPathNotFound` if no element is found
        :raises: :class:`AttributeNotFound` if the element doesn't have the requested attribute
        """

        try:
            return u'%s' % el[0].attrib[self.attr]
        except IndexError:
            return self.default_or_raise(XPathNotFound('Unable to find element %s' % self.selector))
        except KeyError:
            return self.default_or_raise(AttributeNotFound('Element %s does not have attribute %s' % (el[0], self.attr)))


class Link(Attr):
    """
    Get the link uri of an element.

    If the ``<a>`` tag is not found, an exception `IndexError` is raised.
    """

    def __init__(self, selector=None, default=_NO_DEFAULT):
        super(Link, self).__init__(selector, 'href', default=default)


class AbsoluteLink(Link):
    """Get the absolute link URI of an element.
    """
    def __call__(self, item):
        ret = super(AbsoluteLink, self).__call__(item)
        if ret:
            ret = urljoin(item.page.url, ret)
        return ret


class CleanHTML(Filter):
    """Convert HTML to text (Markdown) using html2text.

    .. seealso:: `html2text site <https://pypi.python.org/pypi/html2text>`_
    """

    def __init__(self, selector=None, options=None, default=_NO_DEFAULT):
        """
        :param options: options suitable for html2text
        :type options: dict
        """

        super(CleanHTML, self).__init__(selector=selector, default=default)
        self.options = options

    @debug()
    def filter(self, txt):
        if isinstance(txt, (tuple, list)):
            return u' '.join([self.clean(item, self.options) for item in txt])
        return self.clean(txt, self.options)

    @classmethod
    def clean(cls, txt, options=None):
        if not isinstance(txt, basestring):
            txt = html.tostring(txt, encoding=unicode)
        options = options or {}
        return html2text(txt, **options)


class UnrecognizedElement(Exception):
    pass


class FormValue(Filter):
    """
    Extract a Python value from a form element.

    Checkboxes and radio return booleans, while the rest
    return text. For ``<select>`` tags, returns the user-visible text.
    """

    @debug()
    def filter(self, el):
        try:
            el = el[0]
        except IndexError:
            return self.default_or_raise(XPathNotFound('Unable to find element %s' % self.selector))
        if el.tag == 'input':
            # checkboxes or radios
            if el.attrib.get('type') in ('radio', 'checkbox'):
                return 'checked' in el.attrib
            # regular text input
            elif el.attrib.get('type', '') in ('', 'text', 'email', 'search', 'tel', 'url'):
                try:
                    return unicode(el.attrib['value'])
                except KeyError:
                    return self.default_or_raise(AttributeNotFound('Element %s does not have attribute value' % el))
            # TODO handle html5 number, datetime, etc.
            else:
                raise UnrecognizedElement('Element %s is recognized' % el)
        elif el.tag == 'textarea':
            return unicode(el.text)
        elif el.tag == 'select':
            options = el.xpath('.//option[@selected]')
            # default is the first one
            if len(options) == 0:
                options = el.xpath('.//option[1]')
            return u'\n'.join([unicode(o.text) for o in options])
        else:
            raise UnrecognizedElement('Element %s is recognized' % el)


class HasElement(Filter):
    """
    Returns `yesvalue` if the `selector` finds elements, `novalue` otherwise.
    """
    def __init__(self, selector, yesvalue=True, novalue=False):
        super(HasElement, self).__init__(selector, default=novalue)
        self.yesvalue = yesvalue

    @debug()
    def filter(self, value):
        if value:
            return self.yesvalue
        return self.default_or_raise(FilterError('No default value'))


class ReplaceEntities(CleanText):
    """
    Filter to replace HTML entities like "&eacute;" or "&#x42;" with their unicode counterpart.
    """
    def filter(self, data):
        h = HTMLParser()
        txt = super(ReplaceEntities, self).filter(data)
        return h.unescape(txt)
