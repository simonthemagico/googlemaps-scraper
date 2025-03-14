# -*- coding: utf-8 -*-

import logging
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sys, cgitb
import datetime
import smtplib

__all__ = ['retry', 'mail']


def retry(exceptions_to_check, exc_handler=None, tries=3, delay=2, backoff=2):
    """
    Retry decorator
    from http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from http://wiki.python.org/moin/PythonDecoratorLibrary#Retry
    """
    def deco_retry(f):
        def f_retry(*args, **kwargs):
            mtries = kwargs.pop('_tries', tries)
            mdelay = kwargs.pop('_delay', delay)
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions_to_check as exc:
                    if exc_handler:
                        exc_handler(exc, **kwargs)
                    try:
                        logging.debug(u'%s, Retrying in %d seconds...' % (exc, mdelay))
                    except UnicodeDecodeError:
                        logging.debug(u'%s, Retrying in %d seconds...' % (repr(exc), mdelay))
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)
        return f_retry  # true decorator
    return deco_retry


def mail(from_, to_, host, port, username, password):
    """
    Mail Backtrace Sender decorator
    from https://www.webucator.com/blog/2015/10/creating-an-email-decorator-with-python-and-aws/
    """
    def deco_mail(f):
        def f_mail(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'Error: {0}'.format(str(datetime.datetime.now()), f)
                msg['From'] = from_
                msg['To'] = to_

                text = cgitb.text(sys.exc_info())

                mime_text = MIMEText(text, 'plain')
                msg.attach(mime_text)

                s = smtplib.SMTP(host, port)
                s.starttls()
                s.login(username, password)
                s.send_message(msg)
                s.quit()

                raise e

        return f_mail
    return deco_mail


def loop(time_to_pause=600):
    """
    Loop decorator, to loop a function, and pause between every execution
    :param time_to_pause: int, seconds before next launch
    """
    def deco_loop(f):
        def f_loop(*args, **kwargs):
            while True:
                f(*args, **kwargs)
                for i in range(time_to_pause):
                    logging.info('now pausing {0}'.format(i))
                    time.sleep(1)
        return f_loop
    return deco_loop


