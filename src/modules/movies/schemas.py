from datetime import datetime
from decimal import Decimal
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination wrapper for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# Certification Schemas
class CertificationBase(BaseModel):
    name: str = Field(..., max_length=50)


class CertificationCreate(CertificationBase):
    pass


class CertificationResponse(CertificationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# Genre Schemas
class GenreBase(BaseModel):
    name: str = Field(..., max_length=100)


class GenreCreate(GenreBase):
    pass


class GenreResponse(GenreBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class GenreWithCountResponse(GenreResponse):
    movie_count: int = 0


# Star & Director Schemas
class StarBase(BaseModel):
    name: str = Field(..., max_length=150)


class StarCreate(StarBase):
    pass


class StarResponse(StarBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DirectorBase(BaseModel):
    name: str = Field(..., max_length=150)


class DirectorCreate(DirectorBase):
    pass


class DirectorResponse(DirectorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# Movie Schemas
class MovieBase(BaseModel):
    name: str = Field(..., max_length=255)
    year: int = Field(..., ge=1888, le=2100)
    time: int = Field(..., ge=1, description="Duration in minutes")
    imdb: float = Field(..., ge=0.0, le=10.0)
    votes: int = Field(default=0, ge=0)
    meta_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    gross: Optional[float] = None
    description: str
    price: Decimal = Field(..., ge=Decimal("0.00"), decimal_places=2)
    certification_id: int


class MovieCreate(MovieBase):
    genre_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)


class MovieUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    year: Optional[int] = Field(default=None, ge=1888, le=2100)
    time: Optional[int] = Field(default=None, ge=1)
    imdb: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    votes: Optional[int] = Field(default=None, ge=0)
    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"), decimal_places=2)
    certification_id: Optional[int] = None
    genre_ids: Optional[list[int]] = None
    director_ids: Optional[list[int]] = None
    star_ids: Optional[list[int]] = None


class MovieListItem(BaseModel):
    """Compact movie representation for catalog and favorites listing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: UUID
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    price: Decimal
    certification: CertificationResponse
    genres: list[GenreResponse] = []


class MovieDetailResponse(MovieListItem):
    """Full detailed movie representation."""

    meta_score: Optional[float] = None
    gross: Optional[float] = None
    description: str
    directors: list[DirectorResponse] = []
    stars: list[StarResponse] = []
    likes_count: int = 0
    dislikes_count: int = 0
    average_user_rating: Optional[float] = None
    is_favorite: bool = False


# Rating & Reactions
class MovieRatingCreate(BaseModel):
    rating: int = Field(..., ge=1, le=10)


class MovieRatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    movie_id: int
    rating: int
    created_at: datetime


class MovieReactionCreate(BaseModel):
    is_like: bool  # True = like, False = dislike


class MovieReactionResponse(BaseModel):
    likes_count: int
    dislikes_count: int
    user_reaction: Optional[bool] = None


# Comments & Notifications
class MovieCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: Optional[int] = None


class MovieCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    movie_id: int
    parent_id: Optional[int] = None
    content: str
    created_at: datetime
    likes_count: int = 0


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    message: str
    is_read: bool
    created_at: datetime
