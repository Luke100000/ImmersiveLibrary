from enum import Enum


class ContentOrder(str, Enum):
    DATE = "date"
    LIKES = "likes"
    TITLE = "title"
    REPORTS = "reports"
    RECOMMENDATIONS = "recommendations"
    ADDED = "added"


class UserOrder(str, Enum):
    OID = "date"
    SUBMISSION_COUNT = "submissions"
    LIKES_GIVEN = "likes_given"
    LIKES_RECEIVED = "likes_received"


class RenderPreset(str, Enum):
    EMBED = "embed"
    ICON = "icon"
    THUMBNAIL = "thumbnail"
    SQUARE = "square"


class ContentTrack(str, Enum):
    ALL = "all"
    LIKES = "likes"
    SUBMISSIONS = "submissions"
