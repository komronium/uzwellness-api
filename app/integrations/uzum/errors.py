"""Error codes defined by the Uzum Bank Merchant API protocol.

Uzum expects a failed webhook to answer with HTTP 400 and a JSON body that
carries ``status: FAILED`` plus a string ``errorCode``. The per-endpoint
envelope differs (``/check`` returns a timestamp, ``/create`` returns
``transTime``, ...), so the routers build the body and this module only owns
the vocabulary.

Spec: https://developer.uzumbank.uz/merchant
"""

from __future__ import annotations

from enum import StrEnum


class UzumErrorCode(StrEnum):
    """``errorCode`` values from the "Error Codes" section of the spec."""

    ACCESS_DENIED = "10001"
    JSON_PARSE_ERROR = "10002"
    INVALID_OPERATION = "10003"
    MISSING_PARAMETERS = "10005"
    INVALID_SERVICE_ID = "10006"
    ACCOUNT_NOT_FOUND = "10007"
    ALREADY_PAID = "10008"
    PAYMENT_CANCELLED = "10009"
    TRANSACTION_ALREADY_CREATED = "10010"
    INVALID_AMOUNT = "10011"
    AMOUNT_BELOW_MINIMUM = "10012"
    AMOUNT_ABOVE_MAXIMUM = "10013"
    TRANSACTION_NOT_FOUND = "10014"
    TRANSACTION_CANCELLED = "10015"
    TRANSACTION_ALREADY_CONFIRMED = "10016"
    TRANSACTION_NOT_REVERSIBLE = "10017"
    TRANSACTION_ALREADY_REVERSED = "10018"
    INTERNAL_ERROR = "99999"


class UzumError(Exception):
    """Raised by the service layer; the router turns it into a FAILED body.

    ``detail`` never reaches Uzum — it only goes to our logs, so it can name
    the booking or the amount without leaking anything to the caller.
    """

    def __init__(self, code: UzumErrorCode, detail: str = "") -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail
