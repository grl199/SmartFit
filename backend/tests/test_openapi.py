"""Contract-level checks that do not require a database connection."""
from app.main import app


def test_openapi_operation_ids_are_unique():
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
        and "operationId" in operation
    ]

    assert len(operation_ids) == len(set(operation_ids)), "FastAPI ha generado operationId duplicados"


def test_exercise_content_get_has_single_route():
    schema = app.openapi()
    path = "/exercises/{exercise_id}/content"

    assert path in schema["paths"]
    assert "get" in schema["paths"][path]
    assert "put" in schema["paths"][path]


def test_web_session_endpoints_are_registered():
    schema = app.openapi()["paths"]
    assert "/auth/session/login" in schema
    assert "/auth/session/register" in schema
    assert "/auth/session/refresh" in schema
    assert "/auth/session/logout" in schema
