from enum import Enum


class ContentOrder(str, Enum):
    DATE = "date"
    LIKES = "likes"
    TITLE = "title"
    REPORTS = "reports"
    RECOMMENDATIONS = "recommendations"
    ADDED = "added"
    HOT = "hot"
    POPULAR = "popular"


class UserOrder(str, Enum):
    OID = "date"
    SUBMISSION_COUNT = "submissions"
    LIKES_GIVEN = "likes_given"
    LIKES_RECEIVED = "likes_received"
    RECENT_LIKES_RECEIVED = "recent_likes_received"
    AVERAGE_REPORT_SCORE = "average_report_score"


class RenderPreset(str, Enum):
    EMBED = "embed"
    ICON = "icon"
    THUMBNAIL = "thumbnail"


class ContentTrack(str, Enum):
    ALL = "all"
    LIKES = "likes"
    SUBMISSIONS = "submissions"
