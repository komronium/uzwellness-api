"""Wire schemas for the Uzum Bank Merchant API webhooks.

Field names on the wire are camelCase and fixed by Uzum's specification, so
every field carries an explicit alias instead of relying on a generator —
the mapping is part of the contract and should be readable in one place.

Spec: https://developer.uzumbank.uz/merchant
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ``data`` is an open map of arbitrary keys to ``{"value": "<string>"}``; Uzum
# renders it to the customer in the app.
UzumData = dict[str, dict[str, str]]

TransId = Annotated[str, Field(min_length=1, max_length=64)]


class _UzumModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# --- requests ----------------------------------------------------------------


class UzumCheckRequest(_UzumModel):
    service_id: int = Field(alias="serviceId")
    timestamp: int
    params: dict = Field(default_factory=dict)


class UzumCreateRequest(_UzumModel):
    service_id: int = Field(alias="serviceId")
    timestamp: int
    trans_id: TransId = Field(alias="transId")
    params: dict = Field(default_factory=dict)
    # Payment amount in tiyin (1 UZS = 100 tiyin).
    amount: int


class UzumConfirmRequest(_UzumModel):
    service_id: int = Field(alias="serviceId")
    timestamp: int
    trans_id: TransId = Field(alias="transId")
    payment_source: str | None = Field(default=None, alias="paymentSource")
    tariff: str | None = None
    processing_reference_number: str | None = Field(
        default=None, alias="processingReferenceNumber"
    )
    phone: str | None = None
    card_type: int | None = Field(default=None, alias="cardType")


class UzumReverseRequest(_UzumModel):
    service_id: int = Field(alias="serviceId")
    timestamp: int
    trans_id: TransId = Field(alias="transId")


class UzumStatusRequest(_UzumModel):
    service_id: int = Field(alias="serviceId")
    timestamp: int
    trans_id: TransId = Field(alias="transId")


# --- success responses -------------------------------------------------------


class UzumCheckResponse(_UzumModel):
    service_id: int = Field(serialization_alias="serviceId")
    timestamp: int
    status: Literal["OK"] = "OK"
    data: UzumData = Field(default_factory=dict)


class UzumCreateResponse(_UzumModel):
    service_id: int = Field(serialization_alias="serviceId")
    trans_id: str = Field(serialization_alias="transId")
    status: Literal["CREATED"] = "CREATED"
    trans_time: int = Field(serialization_alias="transTime")
    data: UzumData = Field(default_factory=dict)
    amount: int


class UzumConfirmResponse(_UzumModel):
    service_id: int = Field(serialization_alias="serviceId")
    trans_id: str = Field(serialization_alias="transId")
    status: Literal["CONFIRMED"] = "CONFIRMED"
    confirm_time: int = Field(serialization_alias="confirmTime")
    data: UzumData = Field(default_factory=dict)
    amount: int


class UzumReverseResponse(_UzumModel):
    service_id: int = Field(serialization_alias="serviceId")
    trans_id: str = Field(serialization_alias="transId")
    status: Literal["REVERSED"] = "REVERSED"
    reverse_time: int = Field(serialization_alias="reverseTime")
    data: UzumData = Field(default_factory=dict)
    amount: int


class UzumStatusResponse(_UzumModel):
    service_id: int = Field(serialization_alias="serviceId")
    trans_id: str = Field(serialization_alias="transId")
    status: Literal["CREATED", "CONFIRMED", "REVERSED"]
    trans_time: int = Field(serialization_alias="transTime")
    confirm_time: int | None = Field(default=None, serialization_alias="confirmTime")
    reverse_time: int | None = Field(default=None, serialization_alias="reverseTime")
    data: UzumData = Field(default_factory=dict)
    amount: int | None = None


# --- error response ----------------------------------------------------------


class UzumErrorResponse(_UzumModel):
    """FAILED envelope returned with HTTP 400.

    Uzum only requires ``errorCode``; the surrounding fields echo whatever
    context the failing endpoint has, which is what their examples show.
    """

    service_id: int | None = Field(default=None, serialization_alias="serviceId")
    trans_id: str | None = Field(default=None, serialization_alias="transId")
    status: Literal["FAILED"] = "FAILED"
    timestamp: int | None = None
    trans_time: int | None = Field(default=None, serialization_alias="transTime")
    confirm_time: int | None = Field(default=None, serialization_alias="confirmTime")
    reverse_time: int | None = Field(default=None, serialization_alias="reverseTime")
    error_code: str = Field(serialization_alias="errorCode")
