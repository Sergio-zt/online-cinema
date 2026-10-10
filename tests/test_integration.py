import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash
from src.modules.accounts.models import (
    ActivationToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.modules.movies.models import Certification, Genre, Movie


@pytest.fixture
async def sample_movie(db_session: AsyncSession) -> Movie:
    """Fixture providing a seeded movie with unique title to prevent collisions."""
    cert = await db_session.scalar(
        select(Certification).where(Certification.name == "PG-13")
    )
    if not cert:
        cert = Certification(name="PG-13")
        db_session.add(cert)
        await db_session.flush()

    genre = await db_session.scalar(select(Genre).where(Genre.name == "Sci-Fi"))
    if not genre:
        genre = Genre(name="Sci-Fi")
        db_session.add(genre)
        await db_session.flush()

    unique_title = f"Movie_{uuid.uuid4().hex[:8]}"
    movie = Movie(
        name=unique_title,
        year=2024,
        time=120,
        imdb=8.5,
        votes=1000,
        description="A great test movie for automated integration suites.",
        price=Decimal("9.99"),
        certification_id=cert.id,
        genres=[genre],
    )
    db_session.add(movie)
    await db_session.commit()
    await db_session.refresh(movie)
    return movie


# ==================== 1. PUBLIC ENDPOINTS & UNPROTECTED ACCESS ====================


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test public healthcheck endpoint and database connectivity."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


@pytest.mark.asyncio
async def test_public_movie_catalog_and_filtering(
    client: AsyncClient, sample_movie: Movie
):
    """Test browsing movies without authentication, including filtering."""
    response = await client.get("/api/v1/movies")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1

    # Filter by release year
    filter_response = await client.get(
        "/api/v1/movies", params={"year_from": 2020, "year_to": 2030}
    )
    assert filter_response.status_code == 200
    assert filter_response.json()["total"] >= 1

    # Movie details public view
    detail_response = await client.get(f"/api/v1/movies/{sample_movie.id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == sample_movie.name


@pytest.mark.asyncio
async def test_genres_list_public(client: AsyncClient):
    """Test public genres list with movie count."""
    response = await client.get("/api/v1/genres")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ==================== 2. AUTHENTICATION & ACCESS CONTROL (RBAC) ====================


@pytest.mark.asyncio
async def test_unauthenticated_protected_endpoints_fail(client: AsyncClient):
    """Verify that requests without bearer token return 401 Unauthorized."""
    endpoints = [
        ("GET", "/api/v1/accounts/me"),
        ("GET", "/api/v1/cart"),
        ("POST", "/api/v1/cart/items"),
        ("GET", "/api/v1/orders"),
        ("GET", "/api/v1/payments"),
    ]
    for method, endpoint in endpoints:
        resp = await client.request(method, endpoint)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    """Verify that invalid password returns 401 Unauthorized."""
    resp = await client.post(
        "/api/v1/accounts/login",
        data={"username": "nonexistent@example.com", "password": "WrongPassword1!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_user_forbidden_from_moderator_actions(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify regular user (USER role) receives 403 Forbidden on moderator endpoints."""
    unique_email = f"user_rbac_{uuid.uuid4().hex[:8]}@example.com"
    user_group = await db_session.scalar(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    )
    test_user = User(
        email=unique_email,
        hashed_password=get_password_hash("UserPass123!"),
        is_active=True,
        group_id=user_group.id,  # type: ignore[union-attr]
    )
    db_session.add(test_user)
    await db_session.commit()

    login_resp = await client.post(
        "/api/v1/accounts/login",
        data={"username": test_user.email, "password": "UserPass123!"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to create movie as regular user
    resp = await client.post(
        "/api/v1/movies",
        headers=headers,
        json={
            "name": f"Forbidden_{uuid.uuid4().hex[:6]}",
            "year": 2024,
            "time": 120,
            "imdb": 7.0,
            "description": "Test",
            "price": "5.00",
            "certification_id": 1,
        },
    )
    assert resp.status_code == 403


# ==================== 3. USER REGISTRATION, TOKENS & LOGOUT ====================


@pytest.mark.asyncio
async def test_registration_activation_and_token_refresh(
    client: AsyncClient, db_session: AsyncSession
):
    """Test user registration, email token activation, refresh token, and logout."""
    email = f"full_cycle_{uuid.uuid4().hex[:8]}@example.com"
    password = "FullCyclePassword123!"

    # 1. Register
    reg_resp = await client.post(
        "/api/v1/accounts/register",
        json={"email": email, "password": password},
    )
    assert reg_resp.status_code == 201

    # 2. Duplicate registration check
    dup_resp = await client.post(
        "/api/v1/accounts/register",
        json={"email": email, "password": password},
    )
    assert dup_resp.status_code == 400

    # 3. Retrieve token and activate
    user_record = await db_session.scalar(select(User).where(User.email == email))
    token_record = await db_session.scalar(
        select(ActivationToken).where(ActivationToken.user_id == user_record.id)  # type: ignore[union-attr]
    )
    act_resp = await client.post(
        "/api/v1/accounts/activate",
        json={"token": token_record.token},  # type: ignore[union-attr]
    )
    assert act_resp.status_code == 200

    # 4. Login
    login_resp = await client.post(
        "/api/v1/accounts/login",
        data={"username": email, "password": password},
    )
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    # 5. Refresh token to obtain new access token
    refresh_resp = await client.post(
        "/api/v1/accounts/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()

    # 6. Logout (revokes refresh token)
    logout_resp = await client.post(
        "/api/v1/accounts/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # 7. Using revoked refresh token should now fail
    failed_refresh = await client.post(
        "/api/v1/accounts/refresh",
        json={"refresh_token": refresh_token},
    )
    assert failed_refresh.status_code == 401


# ==================== 4. CART, ORDER, AND PAYMENT BUSINESS RULES ====================


@pytest.mark.asyncio
async def test_cart_order_and_payment_e2e_flow(
    client: AsyncClient, db_session: AsyncSession, sample_movie: Movie
):
    """
    Test complete purchase flow:
    - Add to cart
    - Prevent duplicate in cart
    - Create order from cart
    - Simulate successful payment
    - Verify cart is cleared
    - Verify movie appears in purchased list
    - Verify repeat purchase is rejected
    - Verify moderator cannot delete purchased movie
    """
    email = f"buyer_{uuid.uuid4().hex[:8]}@example.com"
    password = "BuyerPassword123!"

    # 1. Setup active user
    user_group = await db_session.scalar(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    )
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_active=True,
        group_id=user_group.id,  # type: ignore[union-attr]
    )
    db_session.add(user)
    await db_session.commit()

    login_resp = await client.post(
        "/api/v1/accounts/login",
        data={"username": email, "password": password},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Add movie to cart
    add_resp = await client.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"movie_id": sample_movie.id},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["total_items"] == 1

    # 3. Duplicate prevention: adding same movie again must fail with 400
    dup_cart_resp = await client.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"movie_id": sample_movie.id},
    )
    assert dup_cart_resp.status_code == 400

    # 4. Create Order from cart
    order_resp = await client.post("/api/v1/orders", headers=headers)
    assert order_resp.status_code == 201
    order_data = order_resp.json()
    order_id = order_data["id"]
    assert order_data["status"] == "pending"

    # 5. Simulate successful payment
    pay_resp = await client.post(
        f"/api/v1/payments/simulate-success/{order_id}",
        headers=headers,
    )
    assert pay_resp.status_code == 200
    assert pay_resp.json()["status"] == "successful"

    # 6. Verify cart is now empty
    cart_resp = await client.get("/api/v1/cart", headers=headers)
    assert cart_resp.status_code == 200
    assert cart_resp.json()["total_items"] == 0

    # 7. Verify movie appears in purchased list
    purchased_resp = await client.get("/api/v1/movies/purchased", headers=headers)
    assert purchased_resp.status_code == 200
    purchased_ids = [m["id"] for m in purchased_resp.json()]
    assert sample_movie.id in purchased_ids

    # 8. Business Rule: Repeat purchase prevention (cannot add purchased movie to cart)
    repeat_add = await client.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"movie_id": sample_movie.id},
    )
    assert repeat_add.status_code == 400
    assert "already purchased" in repeat_add.json()["detail"].lower()

    # 9. Business Rule: Moderator cannot delete a purchased movie
    mod_email = f"mod_{uuid.uuid4().hex[:8]}@example.com"
    mod_group = await db_session.scalar(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.MODERATOR)
    )
    mod_user = User(
        email=mod_email,
        hashed_password=get_password_hash("ModPassword123!"),
        is_active=True,
        group_id=mod_group.id,  # type: ignore[union-attr]
    )
    db_session.add(mod_user)
    await db_session.commit()

    mod_login = await client.post(
        "/api/v1/accounts/login",
        data={"username": mod_user.email, "password": "ModPassword123!"},
    )
    mod_headers = {"Authorization": f"Bearer {mod_login.json()['access_token']}"}

    del_resp = await client.delete(
        f"/api/v1/movies/{sample_movie.id}",
        headers=mod_headers,
    )
    assert del_resp.status_code == 400
    assert "already been purchased" in del_resp.json()["detail"].lower()
