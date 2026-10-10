from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.modules.accounts.dependencies import (
    get_current_active_user,
    require_roles,
)
from src.modules.accounts.models import User, UserGroupEnum
from src.modules.movies.models import (
    Certification,
    Director,
    Genre,
    Movie,
    MovieComment,
    Star,
)
from src.modules.movies.schemas import (
    CertificationCreate,
    CertificationResponse,
    DirectorCreate,
    DirectorResponse,
    GenreCreate,
    GenreResponse,
    GenreWithCountResponse,
    MovieCommentCreate,
    MovieCommentResponse,
    MovieCreate,
    MovieDetailResponse,
    MovieListItem,
    MovieRatingCreate,
    MovieReactionCreate,
    MovieReactionResponse,
    MovieUpdate,
    PaginatedResponse,
    StarCreate,
    StarResponse,
)
from src.modules.movies.service import MoviesService

router = APIRouter(tags=["Movies Catalog"])


def get_movies_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MoviesService:
    """Dependency providing MoviesService instance."""
    return MoviesService(session)


# ==================== PUBLIC CATALOG & GENRES ====================


@router.get(
    "/genres",
    response_model=list[GenreWithCountResponse],
    summary="Get genres with movie counts",
)
async def list_genres(
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> list[dict]:
    """Retrieve list of genres along with the count of movies in each genre."""
    return await service.list_genres_with_counts()


@router.get(
    "/movies",
    response_model=PaginatedResponse[MovieListItem],
    summary="Browse movie catalog",
)
async def list_movies(
    service: Annotated[MoviesService, Depends(get_movies_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: Optional[str] = Query(
        default=None, description="Search in title, description, star, or director"
    ),
    genre_id: Optional[int] = Query(default=None),
    year_from: Optional[int] = Query(default=None),
    year_to: Optional[int] = Query(default=None),
    imdb_min: Optional[float] = Query(default=None, ge=0.0, le=10.0),
    imdb_max: Optional[float] = Query(default=None, ge=0.0, le=10.0),
    certification_id: Optional[int] = Query(default=None),
    sort_by: Optional[str] = Query(
        default="imdb_desc",
        description=(
            "Sort by: price_asc, price_desc, year_asc, year_desc, "
            "imdb_asc, imdb_desc, votes_desc"
        ),
    ),
) -> PaginatedResponse[MovieListItem]:
    """Browse catalog with full filtering, sorting, searching, and pagination."""
    return await service.list_movies(
        page=page,
        page_size=page_size,
        search=search,
        genre_id=genre_id,
        year_from=year_from,
        year_to=year_to,
        imdb_min=imdb_min,
        imdb_max=imdb_max,
        certification_id=certification_id,
        sort_by=sort_by,
    )


@router.get(
    "/movies/favorites",
    response_model=PaginatedResponse[MovieListItem],
    summary="List user's favorite movies",
)
async def list_favorites(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: Optional[str] = None,
    genre_id: Optional[int] = None,
    sort_by: Optional[str] = "imdb_desc",
) -> PaginatedResponse[MovieListItem]:
    """Retrieve and filter user's favorite movies with catalog capabilities."""
    return await service.list_movies(
        page=page,
        page_size=page_size,
        search=search,
        genre_id=genre_id,
        sort_by=sort_by,
        user_favorites_only_id=current_user.id,
    )


# Статический маршрут /movies/purchased объявлен ДО динамического /movies/{movie_id}
@router.get(
    "/movies/purchased",
    response_model=list[MovieListItem],
    summary="List user's purchased movies",
)
async def list_purchased_movies(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> list[MovieListItem]:
    """Retrieve all movies successfully purchased by the current user."""
    return await service.list_purchased_movies(current_user.id)


@router.get(
    "/movies/{movie_id}",
    response_model=MovieDetailResponse,
    summary="Get movie details",
)
async def get_movie(
    movie_id: int,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> MovieDetailResponse:
    """Retrieve detailed movie specifications, average ratings, and counts."""
    return await service.get_movie_detail(movie_id)


# ==================== USER INTERACTIONS ====================


@router.post(
    "/movies/{movie_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add movie to favorites",
)
async def add_favorite(
    movie_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> None:
    """Add a movie to the user's favorites list."""
    await service.add_to_favorites(current_user.id, movie_id)


@router.delete(
    "/movies/{movie_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove movie from favorites",
)
async def remove_favorite(
    movie_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> None:
    """Remove a movie from the user's favorites list."""
    await service.remove_from_favorites(current_user.id, movie_id)


@router.post(
    "/movies/{movie_id}/rate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rate movie on 10-point scale",
)
async def rate_movie(
    movie_id: int,
    data: MovieRatingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> None:
    """Rate a movie with an integer score from 1 to 10."""
    await service.rate_movie(current_user.id, movie_id, data.rating)


@router.post(
    "/movies/{movie_id}/reaction",
    response_model=MovieReactionResponse,
    summary="Like or dislike a movie",
)
async def react_to_movie(
    movie_id: int,
    data: MovieReactionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> MovieReactionResponse:
    """Toggle like or dislike reaction on a movie."""
    return await service.react_to_movie(current_user.id, movie_id, data.is_like)


@router.post(
    "/movies/{movie_id}/comments",
    response_model=MovieCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write comment or reply on a movie",
)
async def add_comment(
    movie_id: int,
    data: MovieCommentCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> MovieComment:
    """Add a top-level comment or reply to an existing comment on a movie."""
    return await service.add_comment(
        user_id=current_user.id,
        movie_id=movie_id,
        content=data.content,
        parent_id=data.parent_id,
    )


@router.post(
    "/comments/{comment_id}/like",
    summary="Like or unlike a comment",
)
async def like_comment(
    comment_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> dict[str, int]:
    """Toggle like on a comment and notify the author."""
    likes_count = await service.like_comment(current_user.id, comment_id)
    return {"likes_count": likes_count}


# ==================== MODERATOR / ADMIN CRUD ====================


@router.post(
    "/genres",
    response_model=GenreResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Create genre (Moderator/Admin)",
)
async def create_genre(
    data: GenreCreate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Genre:
    """Create a new genre."""
    return await service.create_genre(data)


@router.post(
    "/stars",
    response_model=StarResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Create star/actor (Moderator/Admin)",
)
async def create_star(
    data: StarCreate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Star:
    """Create a new actor/star."""
    return await service.create_star(data)


@router.post(
    "/directors",
    response_model=DirectorResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Create director (Moderator/Admin)",
)
async def create_director(
    data: DirectorCreate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Director:
    """Create a new director."""
    return await service.create_director(data)


@router.post(
    "/certifications",
    response_model=CertificationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Create certification (Moderator/Admin)",
)
async def create_certification(
    data: CertificationCreate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Certification:
    """Create a new movie certification (e.g. PG-13, R)."""
    return await service.create_certification(data)


@router.post(
    "/movies",
    response_model=MovieListItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Create movie (Moderator/Admin)",
)
async def create_movie(
    data: MovieCreate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Movie:
    """Create a new movie in the catalog with genres, directors, and stars."""
    return await service.create_movie(data)


@router.put(
    "/movies/{movie_id}",
    response_model=MovieListItem,
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Update movie (Moderator/Admin)",
)
async def update_movie(
    movie_id: int,
    data: MovieUpdate,
    service: Annotated[MoviesService, Depends(get_movies_service)],
) -> Movie:
    """Update movie specifications and associated relations."""
    return await service.update_movie(movie_id, data)


@router.delete(
    "/movies/{movie_id}",
    dependencies=[Depends(require_roles(UserGroupEnum.MODERATOR, UserGroupEnum.ADMIN))],
    summary="Delete movie (Moderator/Admin)",
)
async def delete_movie(
    movie_id: int,
    service: Annotated[MoviesService, Depends(get_movies_service)],
    confirm_in_cart: bool = Query(
        default=False, description="Confirm deletion if movie is present in user carts"
    ),
) -> dict[str, str]:
    """Delete a movie ensuring it has not been purchased by users."""
    return await service.delete_movie(movie_id, confirm_in_cart=confirm_in_cart)
