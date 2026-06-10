from fastapi import APIRouter, Depends

from app.api.rate_limits import newsletter_rate_limit
from app.schemas.newsletter import (
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
)
from app.services.newsletter_service import NewsletterService, get_newsletter_service

router = APIRouter(prefix="/newsletter", tags=["Newsletter"])


@router.post(
    "/subscribe",
    response_model=NewsletterSubscribeResponse,
    dependencies=[Depends(newsletter_rate_limit)],
)
async def subscribe(
    payload: NewsletterSubscribeRequest,
    newsletter: NewsletterService = Depends(get_newsletter_service),
) -> NewsletterSubscribeResponse:
    subscriber = await newsletter.subscribe(payload.email)
    return NewsletterSubscribeResponse(email=subscriber.email)
