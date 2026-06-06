from collections import Counter

from app.main import app


def _operations(schema: dict):
    methods = {"get", "post", "put", "patch", "delete"}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in methods:
                yield method, path, operation


def test_openapi_contract_has_clean_operation_metadata() -> None:
    schema = app.openapi()
    operations = list(_operations(schema))
    operation_ids = [operation.get("operationId") for _, _, operation in operations]

    assert schema["openapi"].startswith("3.1.")
    assert all(operation.get("tags") for _, _, operation in operations)
    assert [
        key for key, value in Counter(operation_ids).items() if key and value > 1
    ] == []
    assert "ErrorResponse" in schema["components"]["schemas"]


def test_openapi_contract_has_success_response_schemas() -> None:
    schema = app.openapi()

    for method, path, operation in _operations(schema):
        responses = operation.get("responses", {})
        success_codes = [code for code in responses if code.startswith("2")]
        if success_codes == ["204"]:
            continue
        assert any(
            any(
                "schema" in media
                for media in responses[code].get("content", {}).values()
            )
            for code in success_codes
        ), f"{method.upper()} {path} has no success response schema"


def test_openapi_contract_uses_post_for_cancel_actions() -> None:
    schema = app.openapi()

    booking_cancel = schema["paths"]["/api/bookings/{booking_id}/cancel"]
    transfer_cancel = schema["paths"]["/api/transfers/{transfer_id}/cancel"]

    assert "post" in booking_cancel
    assert booking_cancel["patch"]["deprecated"] is True
    assert "post" in transfer_cancel
    assert transfer_cancel["patch"]["deprecated"] is True
