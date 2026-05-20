import struct
import uuid
import zlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.sanatorium import Sanatorium, SanatoriumStatus
from app.models.user import User, UserRole


def make_png(width: int = 1, height: int = 1) -> bytes:
    """Tiny valid PNG, usable to drive multipart uploads in tests."""

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


async def make_user(
    db: AsyncSession,
    *,
    email: str,
    password: str = "passw0rd",
    role: UserRole = UserRole.CUSTOMER,
    is_active: bool = True,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def make_sanatorium(
    db: AsyncSession,
    *,
    name: str | dict = "Test Sanatorium",
    slug: str | None = None,
    city: str = "Toshkent",
    address: str | dict = "Test Address 1",
    stars: int = 4,
    status: SanatoriumStatus = SanatoriumStatus.APPROVED,
    admin_user_id: uuid.UUID | None = None,
    description: dict | None = None,
) -> Sanatorium:
    name_dict = {"uz": name} if isinstance(name, str) else name
    address_dict = {"uz": address} if isinstance(address, str) else address
    primary = next((v for v in name_dict.values() if v), "sanatorium")
    sanatorium = Sanatorium(
        name=name_dict,
        slug=slug or primary.lower().replace(" ", "-"),
        description=description or {},
        city=city,
        address=address_dict,
        stars=stars,
        status=status,
        admin_user_id=admin_user_id,
    )
    db.add(sanatorium)
    await db.commit()
    await db.refresh(sanatorium)
    return sanatorium


class InMemoryStorage:
    """Test storage that keeps bytes in a dict; no disk side effects."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.url_prefix = "/uploads"

    async def save(self, *, key: str, content: bytes, content_type: str) -> str:
        self.objects[key] = content
        return f"{self.url_prefix}/{key}"

    async def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


