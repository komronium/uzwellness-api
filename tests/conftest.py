from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User, UserRole
from app.services.storage import get_storage
from tests.factories import InMemoryStorage

assert settings.TEST_DATABASE_URL is not None, (
    "TEST_DATABASE_URL must be set to run tests"
)
TEST_DB_URL = str(settings.TEST_DATABASE_URL)


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def db(
    session_factory, engine
) -> AsyncGenerator[AsyncSession, None]:
    """Test-side session for fixtures and assertions."""
    async with session_factory() as session:
        yield session

    # Cleanup: truncate all tables to keep tests isolated
    async with engine.begin() as conn:
        table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
async def client(
    db: AsyncSession,
    session_factory,
    storage: InMemoryStorage,
) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_storage] = lambda: storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: UserRole,
    full_name: str = "Test User",
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def customer_user(db: AsyncSession) -> User:
    return await _make_user(
        db,
        email="customer@test.com",
        password="customerpass123",
        role=UserRole.CUSTOMER,
        full_name="Customer One",
    )


@pytest.fixture
async def customer_headers(client: AsyncClient, customer_user: User) -> dict[str, str]:
    return await _login(client, customer_user.email, "customerpass123")


@pytest.fixture
async def admin_user(db: AsyncSession) -> User:
    return await _make_user(
        db,
        email="admin@test.com",
        password="adminpass123",
        role=UserRole.ADMIN,
        full_name="Sanatorium Admin",
    )


@pytest.fixture
async def admin_headers(client: AsyncClient, admin_user: User) -> dict[str, str]:
    return await _login(client, admin_user.email, "adminpass123")


@pytest.fixture
async def super_admin_user(db: AsyncSession) -> User:
    return await _make_user(
        db,
        email="superadmin@test.com",
        password="superpass123",
        role=UserRole.SUPER_ADMIN,
        full_name="Super Admin",
    )


@pytest.fixture
async def super_admin_headers(
    client: AsyncClient, super_admin_user: User
) -> dict[str, str]:
    return await _login(client, super_admin_user.email, "superpass123")
