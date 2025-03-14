# -*- coding: utf-8 -*-

from unittest import TestCase
from lxml.html import fromstring

from core.browser.filters.standard import RawText


class RawTextTest(TestCase):
    # Original RawText behaviour:
    # - the content of <p> is empty, we return the default value
    def test_first_node_is_element(self):
        e = fromstring('<html><body><p></p></body></html>')
        self.assertEqual("foo", RawText('//p', default="foo")(e))

    # - the content of <p> starts with text, we retrieve only that text
    def test_first_node_is_text(self):
        e = fromstring('<html><body><p>blah: <span>229,90</span> EUR</p></body></html>')
        self.assertEqual("blah: ", RawText('//p', default="foo")(e))

    # - the content of <p> starts with a sub-element, we retrieve the default value
    def test_first_node_has_no_recursion(self):
        e = fromstring('<html><body><p><span>229,90</span> EUR</p></body></html>')
        self.assertEqual("foo", RawText('//p', default="foo")(e))

    # Recursive RawText behaviour
    # - the content of <p> starts with text, we retrieve all text, also the text from sub-elements
    def test_first_node_is_text_recursive(self):
        e = fromstring('<html><body><p>blah: <span>229,90</span> EUR</p></body></html>')
        self.assertEqual("blah: 229,90 EUR", RawText('//p', default="foo", children=True)(e))

    # - the content of <p> starts with a sub-element, we retrieve all text, also the text from sub-elements
    def test_first_node_is_element_recursive(self):
        e = fromstring('<html><body><p><span>229,90</span> EUR</p></body></html>')
        self.assertEqual("229,90 EUR", RawText('//p', default="foo", children=True)(e))
