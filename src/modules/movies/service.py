import math
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.movies.models import (
    Certification,
    CommentLike,
    Director,
    Genre,
    Movie,
    MovieComment,
    MovieFavorite,
    MovieRating,
    MovieReaction,
    Notification,
    Star,
    movie_genres,
)
from src.modules.movies.schemas import (
    CertificationCreate,
    CertificationResponse,
    DirectorCreate,
    GenreCreate,
    MovieCreate,
    MovieDetailResponse,
    MovieListItem,
    MovieReactionResponse,
    MovieUpdate,
    PaginatedResponse,
    StarCreate,
)


class MoviesService:
    """Service handling movies catalog, metadata, interactions, and moderation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ==================== GENRES, STARS, DIRECTORS, CERTIFICATIONS ====================

    async def list_genres_with_counts(self) -> list[dict[str, Any]]:
        """Return all genres along with the count of movies assigned to each genre."""
        stmt = (
            select(Genre, func.count(movie_genres.c.movie_id).label("movie_count"))
            .outerjoin(movie_genres, Genre.id == movie_genres.c.genre_id)
            .group_by(Genre.id)
            .order_by(Genre.name.asc())
        )
        results = await self.session.execute(stmt)
        genres_list = []
        for genre, count in results:
            genres_list.append(
                {"id": genre.id, "name": genre.name, "movie_count": count}
            )
        return genres_list

    async def create_genre(self, data: GenreCreate) -> Genre:
        genre = Genre(name=data.name.strip())
        self.session.add(genre)
        await self.session.commit()
        await self.session.refresh(genre)
        return genre

    async def create_star(self, data: StarCreate) -> Star:
        star = Star(name=data.name.strip())
        self.session.add(star)
        await self.session.commit()
        await self.session.refresh(star)
        return star

    async def create_director(self, data: DirectorCreate) -> Director:
        director = Director(name=data.name.strip())
        self.session.add(director)
        await self.session.commit()
        await self.session.refresh(director)
        return director

    async def create_certification(self, data: CertificationCreate) -> Certification:
        cert = Certification(name=data.name.strip())
        self.session.add(cert)
        await self.session.commit()
        await self.session.refresh(cert)
        return cert

    # ==================== MOVIE CATALOG BROWSING & SEARCH ====================

    async def list_movies(
        self,
        page: int = 1,
        page_size: int = 10,
        search: Optional[str] = None,
        genre_id: Optional[int] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        imdb_min: Optional[float] = None,
        imdb_max: Optional[float] = None,
        certification_id: Optional[int] = None,
        sort_by: Optional[str] = "imdb_desc",
        user_favorites_only_id: Optional[int] = None,
    ) -> PaginatedResponse[MovieListItem]:
        """Browse catalog with search, filtering, sorting, and pagination."""
        query = select(Movie).distinct()

        # Joins for search & filter
        if search:
            query = (
                query.outerjoin(Movie.genres)
                .outerjoin(Movie.directors)
                .outerjoin(Movie.stars)
            )
            search_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Movie.name.ilike(search_pattern),
                    Movie.description.ilike(search_pattern),
                    Director.name.ilike(search_pattern),
                    Star.name.ilike(search_pattern),
                )
            )

        if genre_id:
            query = query.join(Movie.genres).where(Genre.id == genre_id)

        if certification_id:
            query = query.where(Movie.certification_id == certification_id)

        if year_from is not None:
            query = query.where(Movie.year >= year_from)

        if year_to is not None:
            query = query.where(Movie.year <= year_to)

        if imdb_min is not None:
            query = query.where(Movie.imdb >= imdb_min)

        if imdb_max is not None:
            query = query.where(Movie.imdb <= imdb_max)

        if user_favorites_only_id is not None:
            query = query.join(Movie.favorites).where(
                MovieFavorite.user_id == user_favorites_only_id
            )

        # Count total matching rows
        count_subquery = query.with_only_columns(
            func.count(distinct(Movie.id))
        ).order_by(None)
        total_count = await self.session.scalar(count_subquery) or 0

        # Sorting
        if sort_by == "price_asc":
            query = query.order_by(Movie.price.asc(), Movie.id.asc())
        elif sort_by == "price_desc":
            query = query.order_by(Movie.price.desc(), Movie.id.asc())
        elif sort_by == "year_asc":
            query = query.order_by(Movie.year.asc(), Movie.id.asc())
        elif sort_by == "year_desc":
            query = query.order_by(Movie.year.desc(), Movie.id.asc())
        elif sort_by == "imdb_asc":
            query = query.order_by(Movie.imdb.asc(), Movie.id.asc())
        elif sort_by == "votes_desc":
            query = query.order_by(Movie.votes.desc(), Movie.id.asc())
        else:
            query = query.order_by(Movie.imdb.desc(), Movie.id.asc())

        # Pagination & Eager Loading
        offset = (page - 1) * page_size
        query = (
            query.offset(offset)
            .limit(page_size)
            .options(
                selectinload(Movie.genres),
                selectinload(Movie.certification),
            )
        )

        movies = (await self.session.scalars(query)).all()
        pages = math.ceil(total_count / page_size) if page_size > 0 else 1

        items = [MovieListItem.model_validate(m) for m in movies]
        return PaginatedResponse(
            items=items,
            total=total_count,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def list_purchased_movies(self, user_id: int) -> list[MovieListItem]:
        """Retrieve all movies successfully purchased by the user."""
        from src.modules.orders.models import Order, OrderItem, OrderStatusEnum

        query = (
            select(Movie)
            .distinct()
            .join(OrderItem, Movie.id == OrderItem.movie_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.user_id == user_id,
                Order.status == OrderStatusEnum.PAID,
            )
            .options(
                selectinload(Movie.genres),
                selectinload(Movie.certification),
            )
        )
        movies = (await self.session.scalars(query)).all()
        return [MovieListItem.model_validate(m) for m in movies]

    async def get_movie_detail(
        self, movie_id: int, current_user_id: Optional[int] = None
    ) -> MovieDetailResponse:
        """Retrieve full movie details including aggregated ratings and reactions."""
        query = (
            select(Movie)
            .where(Movie.id == movie_id)
            .options(
                selectinload(Movie.genres),
                selectinload(Movie.directors),
                selectinload(Movie.stars),
                selectinload(Movie.certification),
            )
        )
        movie = await self.session.scalar(query)
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        likes_count = (
            await self.session.scalar(
                select(func.count(MovieReaction.id)).where(
                    MovieReaction.movie_id == movie_id,
                    MovieReaction.is_like.is_(True),
                )
            )
            or 0
        )
        dislikes_count = (
            await self.session.scalar(
                select(func.count(MovieReaction.id)).where(
                    MovieReaction.movie_id == movie_id,
                    MovieReaction.is_like.is_(False),
                )
            )
            or 0
        )

        avg_rating = await self.session.scalar(
            select(func.avg(MovieRating.rating)).where(MovieRating.movie_id == movie_id)
        )
        average_user_rating = round(float(avg_rating), 1) if avg_rating else None

        is_favorite = False
        if current_user_id:
            fav = await self.session.scalar(
                select(MovieFavorite).where(
                    MovieFavorite.movie_id == movie_id,
                    MovieFavorite.user_id == current_user_id,
                )
            )
            is_favorite = fav is not None

        return MovieDetailResponse(
            id=movie.id,
            uuid=movie.uuid,
            name=movie.name,
            year=movie.year,
            time=movie.time,
            imdb=movie.imdb,
            votes=movie.votes,
            price=movie.price,
            meta_score=movie.meta_score,
            gross=movie.gross,
            description=movie.description,
            certification=CertificationResponse.model_validate(movie.certification),
            genres=movie.genres,
            directors=movie.directors,
            stars=movie.stars,
            likes_count=likes_count,
            dislikes_count=dislikes_count,
            average_user_rating=average_user_rating,
            is_favorite=is_favorite,
        )

    # ==================== USER INTERACTIONS ====================

    async def add_to_favorites(self, user_id: int, movie_id: int) -> None:
        """Add movie to user's favorites list."""
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        existing = await self.session.scalar(
            select(MovieFavorite).where(
                MovieFavorite.user_id == user_id, MovieFavorite.movie_id == movie_id
            )
        )
        if not existing:
            self.session.add(MovieFavorite(user_id=user_id, movie_id=movie_id))
            await self.session.commit()

    async def remove_from_favorites(self, user_id: int, movie_id: int) -> None:
        """Remove movie from user's favorites list."""
        fav = await self.session.scalar(
            select(MovieFavorite).where(
                MovieFavorite.user_id == user_id, MovieFavorite.movie_id == movie_id
            )
        )
        if fav:
            await self.session.delete(fav)
            await self.session.commit()

    async def rate_movie(self, user_id: int, movie_id: int, rating: int) -> None:
        """Rate movie on a 1-10 scale (upsert)."""
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        existing = await self.session.scalar(
            select(MovieRating).where(
                MovieRating.user_id == user_id, MovieRating.movie_id == movie_id
            )
        )
        if existing:
            existing.rating = rating
        else:
            self.session.add(
                MovieRating(user_id=user_id, movie_id=movie_id, rating=rating)
            )
        await self.session.commit()

    async def react_to_movie(
        self, user_id: int, movie_id: int, is_like: bool
    ) -> MovieReactionResponse:
        """Like or dislike a movie."""
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        existing = await self.session.scalar(
            select(MovieReaction).where(
                MovieReaction.user_id == user_id, MovieReaction.movie_id == movie_id
            )
        )
        if existing:
            if existing.is_like == is_like:
                await self.session.delete(existing)
            else:
                existing.is_like = is_like
        else:
            self.session.add(
                MovieReaction(user_id=user_id, movie_id=movie_id, is_like=is_like)
            )
        await self.session.commit()

        likes = (
            await self.session.scalar(
                select(func.count(MovieReaction.id)).where(
                    MovieReaction.movie_id == movie_id,
                    MovieReaction.is_like.is_(True),
                )
            )
            or 0
        )
        dislikes = (
            await self.session.scalar(
                select(func.count(MovieReaction.id)).where(
                    MovieReaction.movie_id == movie_id,
                    MovieReaction.is_like.is_(False),
                )
            )
            or 0
        )

        user_reaction = await self.session.scalar(
            select(MovieReaction.is_like).where(
                MovieReaction.user_id == user_id, MovieReaction.movie_id == movie_id
            )
        )

        return MovieReactionResponse(
            likes_count=likes,
            dislikes_count=dislikes,
            user_reaction=user_reaction,
        )

    async def add_comment(
        self, user_id: int, movie_id: int, content: str, parent_id: Optional[int] = None
    ) -> MovieComment:
        """Write a comment or reply to a comment on a movie."""
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        parent_comment = None
        if parent_id:
            parent_comment = await self.session.scalar(
                select(MovieComment).where(MovieComment.id == parent_id)
            )
            if not parent_comment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent comment not found.",
                )

        new_comment = MovieComment(
            user_id=user_id,
            movie_id=movie_id,
            parent_id=parent_id,
            content=content.strip(),
        )
        self.session.add(new_comment)

        if parent_comment and parent_comment.user_id != user_id:
            notification = Notification(
                user_id=parent_comment.user_id,
                message=f"Someone replied to your comment on movie '{movie.name}'.",
            )
            self.session.add(notification)

        await self.session.commit()
        await self.session.refresh(new_comment)
        return new_comment

    async def like_comment(self, user_id: int, comment_id: int) -> int:
        """Like a comment and notify its author."""
        comment = await self.session.scalar(
            select(MovieComment).where(MovieComment.id == comment_id)
        )
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found."
            )

        existing = await self.session.scalar(
            select(CommentLike).where(
                CommentLike.user_id == user_id, CommentLike.comment_id == comment_id
            )
        )
        if existing:
            await self.session.delete(existing)
        else:
            self.session.add(CommentLike(user_id=user_id, comment_id=comment_id))
            if comment.user_id != user_id:
                notification = Notification(
                    user_id=comment.user_id,
                    message="Someone liked your comment.",
                )
                self.session.add(notification)

        await self.session.commit()
        likes_count = (
            await self.session.scalar(
                select(func.count(CommentLike.id)).where(
                    CommentLike.comment_id == comment_id
                )
            )
            or 0
        )
        return likes_count

    # ==================== MODERATOR CRUD OPERATIONS ====================

    async def create_movie(self, data: MovieCreate) -> Movie:
        """Moderator endpoint to create a movie with relationships."""
        existing = await self.session.scalar(
            select(Movie).where(
                Movie.name == data.name,
                Movie.year == data.year,
                Movie.time == data.time,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A movie with the same title, release year, "
                    "and duration already exists."
                ),
            )

        genres = (
            await self.session.scalars(
                select(Genre).where(Genre.id.in_(data.genre_ids))
            )
        ).all()
        directors = (
            await self.session.scalars(
                select(Director).where(Director.id.in_(data.director_ids))
            )
        ).all()
        stars = (
            await self.session.scalars(select(Star).where(Star.id.in_(data.star_ids)))
        ).all()

        movie = Movie(
            name=data.name.strip(),
            year=data.year,
            time=data.time,
            imdb=data.imdb,
            votes=data.votes,
            meta_score=data.meta_score,
            gross=data.gross,
            description=data.description,
            price=data.price,
            certification_id=data.certification_id,
            genres=list(genres),
            directors=list(directors),
            stars=list(stars),
        )
        self.session.add(movie)
        await self.session.commit()
        await self.session.refresh(movie, attribute_names=["genres", "certification"])
        return movie

    async def update_movie(self, movie_id: int, data: MovieUpdate) -> Movie:
        """Moderator endpoint to update a movie."""
        query = (
            select(Movie)
            .where(Movie.id == movie_id)
            .options(
                selectinload(Movie.genres),
                selectinload(Movie.directors),
                selectinload(Movie.stars),
                selectinload(Movie.certification),
            )
        )
        movie = await self.session.scalar(query)
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        update_dict = data.model_dump(
            exclude_unset=True, exclude={"genre_ids", "director_ids", "star_ids"}
        )
        for key, value in update_dict.items():
            setattr(movie, key, value)

        if data.genre_ids is not None:
            movie.genres = list(
                (
                    await self.session.scalars(
                        select(Genre).where(Genre.id.in_(data.genre_ids))
                    )
                ).all()
            )

        if data.director_ids is not None:
            movie.directors = list(
                (
                    await self.session.scalars(
                        select(Director).where(Director.id.in_(data.director_ids))
                    )
                ).all()
            )

        if data.star_ids is not None:
            movie.stars = list(
                (
                    await self.session.scalars(
                        select(Star).where(Star.id.in_(data.star_ids))
                    )
                ).all()
            )

        await self.session.commit()
        await self.session.refresh(movie, attribute_names=["genres", "certification"])
        return movie

    async def delete_movie(
        self, movie_id: int, confirm_in_cart: bool = False
    ) -> dict[str, str]:
        """
        Delete a movie with strict business constraints:
        1. Prevent deletion if movie has been purchased by at least one user.
        2. Warn/notify if movie is present in user carts.
        """
        movie = await self.session.scalar(select(Movie).where(Movie.id == movie_id))
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found."
            )

        from src.modules.orders.models import Order, OrderItem, OrderStatusEnum

        has_purchases = await self.session.scalar(
            select(OrderItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.status == OrderStatusEnum.PAID,
                OrderItem.movie_id == movie_id,
            )
        )
        if has_purchases:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot delete movie: it has already been purchased "
                    "by at least one user."
                ),
            )

        from src.modules.cart.models import CartItem

        in_cart_count = await self.session.scalar(
            select(func.count(CartItem.id)).where(CartItem.movie_id == movie_id)
        )
        if in_cart_count and not confirm_in_cart:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Warning: This movie is present in {in_cart_count} user cart(s). "
                    f"Pass confirm_in_cart=true query parameter to confirm deletion."
                ),
            )

        await self.session.delete(movie)
        await self.session.commit()
        return {"message": f"Movie '{movie.name}' successfully deleted."}
