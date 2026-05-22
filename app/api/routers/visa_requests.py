import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.api.deps import CurrentUser, not_found, require_roles
from app.core.config import settings
from app.core.pagination import Pagination
from app.core.storage import StorageBackend, detect_document_mime, get_storage
from app.models.user import UserRole
from app.models.visa_request import VisaStatus
from app.schemas.visa_request import (
    VisaRequestCreate,
    VisaRequestList,
    VisaRequestRead,
    VisaStatusUpdate,
)
from app.services.visa_request_service import (
    VisaRequestService,
    get_visa_request_service,
)

router = APIRouter(prefix="/visa-requests", tags=["visa-requests"])

require_super_admin = require_roles(UserRole.SUPER_ADMIN)


@router.get("", response_model=VisaRequestList)
async def list_visa_requests(
    current_user: CurrentUser,
    page: Pagination,
    status_filter: VisaStatus | None = Query(default=None, alias="status"),
    visas: VisaRequestService = Depends(get_visa_request_service),
) -> VisaRequestList:
    items, total = await visas.list_for_user(
        current_user,
        limit=page.limit,
        offset=page.offset,
        status_filter=status_filter,
    )
    return VisaRequestList(
        items=[VisaRequestRead.model_validate(v) for v in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{visa_id}", response_model=VisaRequestRead)
async def get_visa_request(
    visa_id: uuid.UUID,
    current_user: CurrentUser,
    visas: VisaRequestService = Depends(get_visa_request_service),
) -> VisaRequestRead:
    visa = await visas.get_visible(visa_id, current_user)
    if visa is None:
        raise not_found("Visa request not found")
    return VisaRequestRead.model_validate(visa)


@router.post(
    "",
    response_model=VisaRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_visa_request(
    payload: VisaRequestCreate,
    current_user: CurrentUser,
    visas: VisaRequestService = Depends(get_visa_request_service),
) -> VisaRequestRead:
    return VisaRequestRead.model_validate(await visas.create(payload, current_user))


@router.patch(
    "/{visa_id}/status",
    response_model=VisaRequestRead,
    dependencies=[Depends(require_super_admin)],
)
async def update_status(
    visa_id: uuid.UUID,
    payload: VisaStatusUpdate,
    visas: VisaRequestService = Depends(get_visa_request_service),
) -> VisaRequestRead:
    visa = await visas.get_by_id(visa_id)
    if visa is None:
        raise not_found("Visa request not found")
    return VisaRequestRead.model_validate(await visas.update_status(visa, payload))


@router.post(
    "/{visa_id}/upload-passport",
    response_model=VisaRequestRead,
)
async def upload_passport_scan(
    visa_id: uuid.UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    visas: VisaRequestService = Depends(get_visa_request_service),
    storage: StorageBackend = Depends(get_storage),
) -> VisaRequestRead:
    visa = await visas.get_visible(visa_id, current_user)
    if visa is None:
        raise not_found("Visa request not found")
    content, mime = await _read_document(file)
    updated = await visas.attach_passport_scan(
        visa, content=content, content_type=mime, storage=storage
    )
    return VisaRequestRead.model_validate(updated)


@router.post(
    "/{visa_id}/upload-document",
    response_model=VisaRequestRead,
    dependencies=[Depends(require_super_admin)],
)
async def upload_issued_document(
    visa_id: uuid.UUID,
    file: UploadFile = File(...),
    visas: VisaRequestService = Depends(get_visa_request_service),
    storage: StorageBackend = Depends(get_storage),
) -> VisaRequestRead:
    visa = await visas.get_by_id(visa_id)
    if visa is None:
        raise not_found("Visa request not found")
    content, mime = await _read_document(file)
    updated = await visas.attach_issued_document(
        visa, content=content, content_type=mime, storage=storage
    )
    return VisaRequestRead.model_validate(updated)


async def _read_document(file: UploadFile) -> tuple[bytes, str]:
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file"
        )
    mime = detect_document_mime(content)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type (allowed: JPEG, PNG, WebP, PDF)",
        )
    return content, mime
