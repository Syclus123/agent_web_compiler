"""Tests for the REST API server."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
from fastapi.testclient import TestClient  # noqa: E402

from agent_web_compiler.serving.rest_server import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the REST API."""
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health & Schema
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_schema_returns_json_schema(self, client: TestClient) -> None:
        resp = client.get("/schema")
        assert resp.status_code == 200
        schema = resp.json()
        assert "properties" in schema
        assert "blocks" in schema["properties"]


# ---------------------------------------------------------------------------
# Compile endpoint — input validation
# ---------------------------------------------------------------------------


class TestCompileValidation:
    def test_no_source_returns_400(self, client: TestClient) -> None:
        resp = client.post("/v1/compile", json={})
        assert resp.status_code == 400
        assert "Exactly one" in resp.json()["detail"]

    def test_multiple_sources_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"url": "https://example.com", "html": "<html></html>"},
        )
        assert resp.status_code == 400
        assert "Only one" in resp.json()["detail"]

    def test_invalid_mode_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": "<html></html>", "mode": "turbo"},
        )
        assert resp.status_code == 400
        assert "mode" in resp.json()["detail"].lower()

    def test_invalid_render_returns_400(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": "<html></html>", "render": "quantum"},
        )
        assert resp.status_code == 400
        assert "render" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Compile endpoint — HTML compilation
# ---------------------------------------------------------------------------


class TestCompileHTML:
    def test_compile_html_returns_document(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": "<html><body><h1>Hello</h1><p>World</p></body></html>"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "schema_version" in data
        assert "blocks" in data
        assert "actions" in data

    def test_compile_markdown_returns_markdown(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/markdown",
            json={"html": "<html><body><h1>Title</h1><p>Content</p></body></html>"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "markdown" in data
        assert isinstance(data["markdown"], str)

    def test_compile_blocks_returns_blocks(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/blocks",
            json={"html": "<html><body><h1>Hello</h1><p>World</p></body></html>"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        assert isinstance(data["blocks"], list)

    def test_compile_blocks_with_min_importance(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/blocks",
            json={
                "html": "<html><body><h1>Hello</h1><p>World</p></body></html>",
                "min_importance": 0.9,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        # All returned blocks should meet the threshold
        for block in data["blocks"]:
            assert block["importance"] >= 0.9

    def test_compile_blocks_with_type_filter(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/blocks",
            json={
                "html": "<html><body><h1>Hello</h1><p>World</p></body></html>",
                "block_types": ["heading"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for block in data["blocks"]:
            assert block["type"] == "heading"

    def test_compile_actions_returns_actions(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/actions",
            json={
                "html": '<html><body><a href="https://example.com">Link</a></body></html>'
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "actions" in data
        assert isinstance(data["actions"], list)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCORS:
    def test_cors_headers_present(self, client: TestClient) -> None:
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------------


class TestResponseHeaders:
    def test_compile_returns_compile_time_header(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": "<html><body><h1>Hello</h1></body></html>"},
        )
        assert resp.status_code == 200
        assert "x-compile-time-ms" in resp.headers
        compile_time = int(resp.headers["x-compile-time-ms"])
        assert compile_time >= 0

    def test_compile_returns_block_count_header(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": "<html><body><h1>Hello</h1><p>World</p></body></html>"},
        )
        assert resp.status_code == 200
        assert "x-block-count" in resp.headers
        block_count = int(resp.headers["x-block-count"])
        assert block_count > 0

    def test_compile_returns_action_count_header(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile",
            json={"html": '<html><body><a href="/link">Click</a></body></html>'},
        )
        assert resp.status_code == 200
        assert "x-action-count" in resp.headers

    def test_markdown_endpoint_has_headers(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/markdown",
            json={"html": "<html><body><p>Test</p></body></html>"},
        )
        assert resp.status_code == 200
        assert "x-compile-time-ms" in resp.headers

    def test_blocks_endpoint_has_headers(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/blocks",
            json={"html": "<html><body><p>Test</p></body></html>"},
        )
        assert resp.status_code == 200
        assert "x-block-count" in resp.headers

    def test_actions_endpoint_has_headers(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/compile/actions",
            json={"html": "<html><body><p>Test</p></body></html>"},
        )
        assert resp.status_code == 200
        assert "x-action-count" in resp.headers


# ---------------------------------------------------------------------------
# Error sanitization
# ---------------------------------------------------------------------------


class TestErrorSanitization:
    """Verify error responses don't leak internal details."""

    def test_compilation_error_no_stack_trace(self, client: TestClient) -> None:
        """Compile errors should return structured error, not raw exception text."""
        # This test verifies the error format; actual compilation errors
        # are hard to trigger without network, so we just verify the
        # error format for validation errors is clean.
        resp = client.post("/v1/compile", json={})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert "Traceback" not in detail
