from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

# Association Tables
movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column(
        "movie_id",
        Integer,
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        Integer,
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

movie_directors = Table(
    "movie_directors",
    Base.metadata,
    Column(
        "movie_id",
        Integer,
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "director_id",
        Integer,
        ForeignKey("directors.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

movie_stars = Table(
    "movie_stars",
    Base.metadata,
    Column(
        "movie_id",
        Integer,
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "star_id",
        Integer,
        ForeignKey("stars.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Genre(Base):
    """Movie genre entity (e.g., Action, Drama, Comedy)."""

    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Relationships
    movies: Mapped[list[Movie]] = relationship(
        "Movie", secondary=movie_genres, back_populates="genres"
    )


class Star(Base):
    """Actor or actress starring in movies."""

    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )

    # Relationships
    movies: Mapped[list[Movie]] = relationship(
        "Movie", secondary=movie_stars, back_populates="stars"
    )


class Director(Base):
    """Movie director entity."""

    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )

    # Relationships
    movies: Mapped[list[Movie]] = relationship(
        "Movie", secondary=movie_directors, back_populates="directors"
    )


class Certification(Base):
    """Rating certification of a movie (e.g., PG-13, R)."""

    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Relationships
    movies: Mapped[list[Movie]] = relationship("Movie", back_populates="certification")


class Movie(Base):
    """Movie entity storing primary metadata and financial information."""

    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("name", "year", "time", name="uq_movies_name_year_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), default=uuid4, unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    time: Mapped[int] = mapped_column(Integer, nullable=False)  # Duration in minutes
    imdb: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    certification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certifications.id", ondelete="RESTRICT"), nullable=False
    )

    # Relationships
    certification: Mapped[Certification] = relationship(
        "Certification", back_populates="movies"
    )
    genres: Mapped[list[Genre]] = relationship(
        "Genre", secondary=movie_genres, back_populates="movies"
    )
    directors: Mapped[list[Director]] = relationship(
        "Director", secondary=movie_directors, back_populates="movies"
    )
    stars: Mapped[list[Star]] = relationship(
        "Star", secondary=movie_stars, back_populates="movies"
    )
    favorites: Mapped[list[MovieFavorite]] = relationship(
        "MovieFavorite", back_populates="movie", cascade="all, delete-orphan"
    )
    ratings: Mapped[list[MovieRating]] = relationship(
        "MovieRating", back_populates="movie", cascade="all, delete-orphan"
    )
    reactions: Mapped[list[MovieReaction]] = relationship(
        "MovieReaction", back_populates="movie", cascade="all, delete-orphan"
    )
    comments: Mapped[list[MovieComment]] = relationship(
        "MovieComment", back_populates="movie", cascade="all, delete-orphan"
    )


class MovieFavorite(Base):
    """User favorite movies junction table."""

    __tablename__ = "movie_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_favorites_user_movie"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    movie: Mapped[Movie] = relationship("Movie", back_populates="favorites")


class MovieRating(Base):
    """User rating for movies on a 1-10 scale."""

    __tablename__ = "movie_ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_ratings_user_movie"),
        CheckConstraint("rating >= 1 AND rating <= 10", name="ck_movie_ratings_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    movie: Mapped[Movie] = relationship("Movie", back_populates="ratings")


class MovieReaction(Base):
    """Likes and dislikes on movies."""

    __tablename__ = "movie_reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_movie_reactions_user_movie"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    is_like: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )  # True = like, False = dislike

    # Relationships
    movie: Mapped[Movie] = relationship("Movie", back_populates="reactions")


class MovieComment(Base):
    """User comments on movies with support for nested replies."""

    __tablename__ = "movie_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    movie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("movie_comments.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    movie: Mapped[Movie] = relationship("Movie", back_populates="comments")
    likes: Mapped[list[CommentLike]] = relationship(
        "CommentLike", back_populates="comment", cascade="all, delete-orphan"
    )
    replies: Mapped[list[MovieComment]] = relationship(
        "MovieComment",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional[MovieComment]] = relationship(
        "MovieComment", back_populates="replies", remote_side=[id]
    )


class CommentLike(Base):
    """Likes on movie comments."""

    __tablename__ = "comment_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_comment_likes_user_comment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("movie_comments.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    comment: Mapped[MovieComment] = relationship("MovieComment", back_populates="likes")


class Notification(Base):
    """User notification entity for comment replies or likes."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
