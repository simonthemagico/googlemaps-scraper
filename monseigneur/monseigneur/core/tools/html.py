# -*- coding: utf-8 -*-

from monseigneur.monseigneur.core.tools.compat import unicode

__all__ = ['html2text']


from html2text import HTML2Text


def html2text(html, **options):
    h = HTML2Text()
    defaults = dict(
        unicode_snob=True,
        skip_internal_links=True,
        inline_links=False,
        links_each_paragraph=True,
    )
    defaults.update(options)
    for k, v in defaults.items():
        setattr(h, k, v)
    return unicode(h.handle(html))
