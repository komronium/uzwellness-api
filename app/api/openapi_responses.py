from app.schemas.common import ErrorResponse

COMMON_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    # Both are produced centrally in app/api/error_handlers.py, so no router
    # declares them and clients would otherwise not know they are JSON too.
    500: {
        "model": ErrorResponse,
        "description": "Unexpected failure; `detail` carries a reference code",
    },
    503: {
        "model": ErrorResponse,
        "description": "A dependency (database, exchange rate, Uzum) is unavailable",
    },
}
