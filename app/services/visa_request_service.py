import uuid
from collections.abc import Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.booking_attachment import resolve_owner_for_booking
from app.core.config import settings
from app.core.database import get_db
from app.core.ids import uuid7
from app.core.pagination import paginated
from app.core.storage import MIME_EXTENSIONS, StorageBackend
from app.models.user import User, UserRole
from app.models.visa_request import VisaRequest, VisaStatus
from app.schemas.visa_request import VisaRequestCreate, VisaStatusUpdate


class VisaRequestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, visa_id: uuid.UUID) -> VisaRequest | None:
        return await self.db.get(VisaRequest, visa_id)

    async def get_visible(
        self, visa_id: uuid.UUID, user: User
    ) -> VisaRequest | None:
        visa = await self.get_by_id(visa_id)
        if visa is None:
            return None
        if user.role == UserRole.SUPER_ADMIN:
            return visa
        if visa.user_id == user.id:
            return visa
        return None

    async def list_for_user(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        status_filter: VisaStatus | None = None,
    ) -> tuple[Sequence[VisaRequest], int]:
        stmt = select(VisaRequest).order_by(VisaRequest.created_at.desc())
        if user.role != UserRole.SUPER_ADMIN:
            stmt = stmt.where(VisaRequest.user_id == user.id)
        if status_filter is not None:
            stmt = stmt.where(VisaRequest.status == status_filter)
        return await paginated(self.db, stmt, limit=limit, offset=offset)

    async def create(self, payload: VisaRequestCreate, user: User) -> VisaRequest:
        owner_id = await resolve_owner_for_booking(
            self.db,
            booking_id=payload.booking_id,
            actor=user,
            resource_label="visa request",
        )
        visa = VisaRequest(
            user_id=owner_id,
            booking_id=payload.booking_id,
            full_name=payload.full_name,
            citizenship=payload.citizenship,
            passport_number=payload.passport_number,
            date_of_birth=payload.date_of_birth,
            arrival_date=payload.arrival_date,
            departure_date=payload.departure_date,
            purpose=payload.purpose,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            status=VisaStatus.PENDING,
        )
        self.db.add(visa)
        await self.db.commit()
        await self.db.refresh(visa)
        return visa

    async def update_status(
        self, visa: VisaRequest, payload: VisaStatusUpdate
    ) -> VisaRequest:
        visa.status = payload.status
        if payload.admin_notes is not None:
            visa.admin_notes = payload.admin_notes
        await self.db.commit()
        await self.db.refresh(visa)
        return visa

    async def attach_passport_scan(
        self,
        visa: VisaRequest,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
    ) -> VisaRequest:
        url = await self._save_document(
            visa,
            content=content,
            content_type=content_type,
            storage=storage,
            subdir="passport",
        )
        if visa.passport_scan_url is not None:
            await self._delete_url(visa.passport_scan_url, storage)
        visa.passport_scan_url = url
        await self.db.commit()
        await self.db.refresh(visa)
        return visa

    async def attach_issued_document(
        self,
        visa: VisaRequest,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
    ) -> VisaRequest:
        url = await self._save_document(
            visa,
            content=content,
            content_type=content_type,
            storage=storage,
            subdir="document",
        )
        if visa.issued_document_url is not None:
            await self._delete_url(visa.issued_document_url, storage)
        visa.issued_document_url = url
        await self.db.commit()
        await self.db.refresh(visa)
        return visa

    @staticmethod
    async def _save_document(
        visa: VisaRequest,
        *,
        content: bytes,
        content_type: str,
        storage: StorageBackend,
        subdir: str,
    ) -> str:
        ext = MIME_EXTENSIONS[content_type]
        key = f"visa_requests/{visa.id}/{subdir}-{uuid7()}.{ext}"
        return await storage.save(
            key=key, content=content, content_type=content_type
        )

    @staticmethod
    async def _delete_url(url: str, storage: StorageBackend) -> None:
        prefix = settings.UPLOAD_URL_PREFIX.rstrip("/") + "/"
        key = url[len(prefix):] if url.startswith(prefix) else url
        await storage.delete(key=key)


def get_visa_request_service(
    db: AsyncSession = Depends(get_db),
) -> VisaRequestService:
    return VisaRequestService(db)
