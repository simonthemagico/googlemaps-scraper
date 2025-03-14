from datetime import datetime
from typing import List, Dict, Any, Optional, Union


class RunUserTaskResult:
    """
    Regular Python class equivalent to SQLAlchemy RunUserTaskResult
    """
    def __init__(self, result_id: Optional[int] = None, **kwargs):
        self.result_id = result_id
        for key, value in kwargs.items():
            setattr(self, key, value)


class Activity:
    """
    Regular Python class equivalent to SQLAlchemy Activity
    """
    def __init__(
        self,
        id: Optional[int] = None,
        activity: Optional[str] = None,
        appearance: Optional[int] = None,
        language_code: Optional[str] = None,
        gcid: Optional[str] = None
    ):
        self.id = id
        self.activity = activity
        self.appearance = appearance
        self.language_code = language_code
        self.gcid = gcid

    def __str__(self) -> str:
        return self.activity or ""


class Result:
    """
    Regular Python class equivalent to SQLAlchemy Result
    """
    def __init__(
        self,
        id: Optional[int] = None,
        zero_x: Optional[str] = None,
        cid: Optional[str] = None,
        name: Optional[str] = None,
        address: Optional[str] = None,
        country: Optional[str] = None,
        country_code: Optional[str] = None,
        zip_code: Optional[str] = None,
        city: Optional[str] = None,
        description: Optional[str] = None,
        main_image_url: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        url: Optional[str] = None,
        ratings: Optional[int] = None,
        score: Optional[float] = None,
        category: Optional[str] = None,
        special_category: Optional[str] = None,
        phone: Optional[str] = None,
        website: Optional[str] = None,
        menu: Optional[str] = None,
        plus_code: Optional[str] = None,
        is_temporarily_closed: bool = False,
        is_permanently_closed: bool = False,
        opening_hours: Optional[str] = None,
        poi: Optional[str] = None,
        price: Optional[str] = None,
        images_count: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        last_opening_hours_updated_at: Optional[str] = None,
        has_owner: Optional[bool] = None,
        booking_link: Optional[str] = None,
        health: Optional[bool] = None,
        popular_times: Optional[str] = None,
        about: Optional[Dict[str, Any]] = None,
        email: Optional[str] = None,
        facebook: Optional[str] = None,
        instagram: Optional[str] = None,
        additional_phone: Optional[str] = None,
        metadata_activity: Optional[str] = None,
        metadata_city: Optional[str] = None,
        metadata_country: Optional[str] = None,
        classified_emails: Optional[Dict[str, Any]] = None,
        ai_emails_discovery: Optional[Dict[str, Any]] = None,
        ai_emails_discovery_done: bool = False,
        ai_emails_discovery_time: Optional[datetime] = None,
        raw_ai_answer: Optional[str] = None,
        scraping_time: Optional[datetime] = None,
        filling_details: Optional[Dict[str, Any]] = None
    ):
        self.id = id
        self.zero_x = zero_x
        self.cid = cid
        self.name = name
        self.address = address
        self.country = country
        self.country_code = country_code
        self.zip_code = zip_code
        self.city = city
        self.description = description
        self.main_image_url = main_image_url
        self.lat = lat
        self.lng = lng
        self.url = url
        self.ratings = ratings
        self.score = score
        self.category = category
        self.special_category = special_category
        self.phone = phone
        self.website = website
        self.menu = menu
        self.plus_code = plus_code
        self.is_temporarily_closed = is_temporarily_closed
        self.is_permanently_closed = is_permanently_closed
        self.opening_hours = opening_hours
        self.poi = poi
        self.price = price
        self.images_count = images_count
        self.images = images or []
        self.last_opening_hours_updated_at = last_opening_hours_updated_at
        self.has_owner = has_owner
        self.booking_link = booking_link
        self.health = health
        self.popular_times = popular_times
        self.about = about or {}
        self.email = email
        self.facebook = facebook
        self.instagram = instagram
        self.additional_phone = additional_phone
        self.metadata_activity = metadata_activity
        self.metadata_city = metadata_city
        self.metadata_country = metadata_country
        self.classified_emails = classified_emails or {}
        self.ai_emails_discovery = ai_emails_discovery or {}
        self.ai_emails_discovery_done = ai_emails_discovery_done
        self.ai_emails_discovery_time = ai_emails_discovery_time
        self.raw_ai_answer = raw_ai_answer
        self.scraping_time = scraping_time
        self.filling_details = filling_details or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the Result object to a dictionary
        """
        return {
            key: value for key, value in self.__dict__.items()
            if not key.startswith('_')
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Result':
        """
        Create a Result object from a dictionary
        """
        return cls(**data)


class Contact:
    """
    Regular Python class equivalent to SQLAlchemy Contact
    """
    def __init__(
        self,
        id: Optional[int] = None,
        value: Optional[str] = None,
        type: Optional[str] = None,  # mail or phone or social_media
        usage: Optional[str] = None,  # personal or professional
        source: Optional[str] = None,
        domain: Optional[str] = None,
        extracted_on: Optional[datetime] = None,
        task_id: Optional[int] = None
    ):
        self.id = id
        self.value = value
        self.type = type
        self.usage = usage
        self.source = source
        self.domain = domain
        self.extracted_on = extracted_on
        self.task_id = task_id


class EmailClassification:
    """
    Regular Python class equivalent to SQLAlchemy EmailClassification
    """
    def __init__(
        self,
        id: Optional[int] = None,
        email: Optional[str] = None,
        classification: Optional[int] = None,  # 0 for bad, 1 for good
        confidence: Optional[float] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.email = email
        self.classification = classification
        self.confidence = confidence
        self.created_at = created_at or datetime.now()

    def __repr__(self) -> str:
        return f"<EmailClassification(email='{self.email}', classification={self.classification}, confidence={self.confidence})>" 