import re


class Regex(object):

    mail = re.compile(r"[\w\.\-]{2,100}\@[\w\-]{2,100}\.[a-z]{2,100}\.*[a-z]*(?=\s|$|\"|\<|\?|\>|\(|\))")
    phone = re.compile(r"(?<=\s|\"|<|\?|>|\(|\)|:)(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})(?=\s|$|\"|<|\?|>|\(|\))")
    personal_phone = re.compile(r"(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[6-7]")
    instagram = re.compile(r'(?<=href=")https?:\/\/(?:www\.)?instagram\.com\/(?!reel|p|tags)[^"]+', re.IGNORECASE)
    facebook = re.compile(r"(?<=href=\")http(?:s)?\:\/\/(?:.[a-z-]+\.)?facebook\.com\/(?!watch|login|\?|meta|help|privacy|policy|share|photo|term|menu|event|plugin)[^\"]+", re.IGNORECASE)
    twitter = re.compile(r"(?<=href=\")http(?:s)?\:\/\/(?:www\.)?twitter\.com/(?!search|i\/web|intent|pwscontact|hashtag|share)[^\"]+", re.IGNORECASE)
    linkedin = re.compile(r"(?<=href=\")http(?:s)?\:\/\/www\.linkedin\.com\/(?:company|in)\/[^\"]+")
    youtube = re.compile(r"(?<=href=\")http(?:s)?\:\/\/www\.youtube\.com\/c(?:hannel)?\/[^\"]+")
    viadeo = re.compile(r"(?<=href=\")http(?:s)?\:\/\/(?:.[a-z-]+\.)?viadeo\.com\/.[^\"]+\/company[^\"]+")

    price = re.compile(r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})?(?=\s?\€|\$|\£)")
    siret = re.compile(r"(?<=[^0-9]{1})\d{3}\s?\d{3}\s?\d{3}\s?\d{5}(?=[^0-9]{1})")

    def __repr__(self):
        return Regex
