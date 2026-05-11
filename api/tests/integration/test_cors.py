import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_preflight_allows_sveltekit_dev_origin(async_client: AsyncClient):
    response = await async_client.options(
        "/api/v1/conversations",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


@pytest.mark.asyncio
async def test_cors_preflight_rejects_unknown_origin(async_client: AsyncClient):
    response = await async_client.options(
        "/api/v1/conversations",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Without a matching allow-origin header the browser will block the call.
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}
