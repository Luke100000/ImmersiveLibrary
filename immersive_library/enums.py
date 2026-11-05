from enum import Enum


class ContentOrder(str, Enum):
    DATE = "date"
    LIKES = "likes"
    TITLE = "title"
    REPORT_SCORE = "report_score"
    RELEVANCE = "relevance"
    RECOMMENDATIONS = "recommendations"
    ADDED = "added"
    HOT = "hot"
    POPULAR = "popular"


class UserOrder(str, Enum):
    DATE = "date"
    SUBMISSION_COUNT = "submissions"
    LIKES_GIVEN = "likes_given"
    LIKES_RECEIVED = "likes_received"
    RECENT_LIKES_RECEIVED = "recent_likes_received"
    REPORT_SCORE = "report_score"


class CollectionOrder(str, Enum):
    RELEVANCE = "relevance"
    RECOMMENDATIONS = "recommendations"
    CONTENT_COUNT = "content_count"
    DATE = "date"
    UPDATED = "updated"
    TITLE = "title"


class Inclusion(str, Enum):
    EXCLUDE = "exclude"
    INCLUDE = "include"
    ONLY = "only"


class RenderPreset(str, Enum):
    EMBED = "embed"
    ICON = "icon"
    THUMBNAIL = "thumbnail"


class ContentTrack(str, Enum):
    ALL = "all"
    LIKES = "likes"
    SUBMISSIONS = "submissions"


class SitemapSection(str, Enum):
    CONTENT = "content"
    COLLECTIONS = "collections"
