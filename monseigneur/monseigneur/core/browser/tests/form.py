# -*- coding: utf-8 -*-

import collections
import warnings
from unittest import TestCase

import lxml.html

from monseigneur.core.browser import URL
from core.browser.pages import Form, FormSubmitWarning


# Mock that allows to represent a Page
class MyMockPage(object):
    url = URL("http://httpbin.org")


# Class that tests different methods from the class URL
class FormTest(TestCase):

    # Initialization of the objects needed by the tests
    def setUp(self):
        self.page = MyMockPage()
        self.el = lxml.html.fromstring(
            """<form method='GET'>
                   <input type ='text' name='nom' value='Dupont'/>
                   <input type ='text' name='prenom' value=''/>
                   <select name='mySelect'>
                       <option value='item1'>item1</option>
                       <option selected='true' value='item2'>item2</option>
                   </select>
                   <select name='mySelectNotSelected'>
                       <option value='item1'>item1</option>
                       <option value='item2'>item2</option>
                   </select>
                   <input type='submit' name='submitForm' />
               </form>""")
        self.elMoreSubmit = lxml.html.fromstring(
            """<form method='GET'>
                   <input type ='text' name='nom' value='Dupont'/>
                   <input type ='text' name='prenom' value=''/>
                   <select name='mySelect'>
                       <option value='item1'>item1</option>
                       <option selected='true' value='item2'>item2</option>
                   </select>
                   <select name='mySelectNotSelected'>
                       <option value='item1'>item1</option>
                       <option value='item2'>item2</option>
                   </select>
                   <input type='submit' name='submitForm'/>
                   <input type='submit' name='submit2'/>
                </form>""")

    # Checks that the dictionary is correctly initialised
    def test_init_nominal_case(self):
        form = Form(self.page, self.el, None)
        self.assertDictEqual(form, collections.OrderedDict([
            ('nom', 'Dupont'), ('prenom', ''), ('mySelect', 'item2'),
            ('mySelectNotSelected', 'item1'), ('submitForm', u'')]))

    # Checks that submit fields are not added to the dictionary when the
    # attribute submit_el is set to False
    def test_no_submit(self):
        formNoSubmit = Form(self.page, self.el, False)
        self.assertDictEqual(formNoSubmit, collections.OrderedDict([
            ('nom', 'Dupont'), ('prenom', ''), ('mySelect', 'item2'),
            ('mySelectNotSelected', 'item1')]))

    # Checks that the right warning is issued when there are several submit
    # fields
    def test_warning_more_submit(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Form(self.page, self.elMoreSubmit)
            warningMsg = "Form has more than one submit input, you" + \
                         " should chose the correct one"
            assert len(w) == 1
            assert issubclass(w[-1].category, FormSubmitWarning)
            assert warningMsg in str(w[-1].message)

    # Checks that a warning is raised when the submit passed as a parameter
    # does not exist in the form
    def test_warning_submit_not_find(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Form(self.page, self.el, lxml.html.fromstring(
                "<input type='submit' name='submitNotFind' />"))
            warningMsg = "Form had a submit element provided, but" + \
                         " it was not found"
            assert len(w) == 1
            assert issubclass(w[-1].category, FormSubmitWarning)
            assert warningMsg in str(w[-1].message)
