from collections import Counter
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.mapping import map_customer, map_products
from app.upstreams import UpstreamError, Upstreams

KEY = "test-key-at-least-16-chars"
SETTINGS = Settings(core_url="https://core.test/users/{id}",
                    products_url="https://products.test/carts/{id}",
                    fx_url="https://fx.test/latest", api_key=KEY,
                    timeout_seconds=0.05, backoff_seconds=0, fx_ttl_seconds=60)
CORE = {"id": 1, "firstName": "Ana", "lastName": "Pérez", "email": "ana@example.test",
        "phone": "+50700000000", "address": {"address": "Calle 1", "city": "Panamá", "country": "Panamá"},
        "password": "SENSITIVE_PASSWORD", "ssn": "SENSITIVE_SSN",
        "bank": {"cardNumber": "SENSITIVE_CARD"}, "crypto": {"wallet": "SENSITIVE_WALLET"}}
CARTS = {"total": 1, "carts": [{"userId": 1, "total": 999999, "discountedTotal": 1,
          "products": [{"id": 10, "title": "Producto", "price": 10, "quantity": 3,
                        "discountPercentage": 10, "total": 666, "discountedTotal": 777}]}]}
FX = {"base": "USD", "date": "2026-10-30", "rates": {"EUR": 0.9, "GBP": 0.8}}


def handler(request):
    return httpx.Response(200, json={"core.test": CORE, "products.test": CARTS, "fx.test": FX}[request.url.host])


def client_for(callback=handler, settings=SETTINGS):
    return TestClient(create_app(settings, httpx.MockTransport(callback)))


def test_mapping_allowlist_and_recalculated_money():
    mapped = map_customer(CORE, 1).model_dump_json()
    assert "Ana Pérez" in mapped
    assert "SENSITIVE" not in mapped
    products = map_products(CARTS, 1)
    assert products.grossTotalUsd == Decimal("30.00")
    assert products.netTotalUsd == Decimal("27.00")
    assert products.discountTotalUsd == Decimal("3.00")
    assert products.units == 3


def test_profile_and_request_id_propagation():
    seen = []
    def upstream(request):
        seen.append(request.headers["X-Request-Id"])
        return handler(request)
    with client_for(upstream) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY, "X-Request-Id": "demo-123"})
    assert response.status_code == 200
    assert response.json()["partial"] is False
    assert response.json()["products"]["netTotalUsd"] == "27.00"
    assert "SENSITIVE" not in response.text
    assert set(seen) == {"demo-123"}
    assert response.headers["X-Request-Id"] == "demo-123"


@pytest.mark.parametrize("provider", ["core.test", "products.test"])
@pytest.mark.parametrize("status,attempts", [(500, 2), (503, 2), (404, 1), (429, 1), (401, 1)])
def test_degradation_and_retry_rules(provider, status, attempts):
    calls = Counter()
    def upstream(request):
        calls[request.url.host] += 1
        return httpx.Response(status) if request.url.host == provider else handler(request)
    with client_for(upstream) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
    assert response.status_code == 200
    data = response.json()
    assert data["partial"] is True
    assert data["customer" if provider == "core.test" else "products"] is None
    assert data["products" if provider == "core.test" else "customer"] is not None
    assert calls[provider] == attempts


def test_both_upstreams_fail_still_200():
    with client_for(lambda request: httpx.Response(500)) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
    assert response.status_code == 200
    assert response.json()["partial"] is True
    assert response.json()["customer"] is None
    assert response.json()["products"] is None
    assert len(response.json()["warnings"]) == 2


@pytest.mark.parametrize("headers", [{}, {"X-Api-Key": "wrong"}])
def test_auth_denied_without_upstream_calls(headers):
    def no_calls(request):
        pytest.fail("Authentication must run before calling upstreams")
    with client_for(no_calls) as client:
        response = client.get("/api/v1/customers/1/profile", headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("customer_id", ["0", "-1", "abc", "2147483648"])
def test_invalid_id(customer_id):
    with client_for() as client:
        assert client.get(f"/api/v1/customers/{customer_id}/profile", headers={"X-Api-Key": KEY}).status_code == 422


@pytest.mark.asyncio
async def test_timeout_retried_and_bounded():
    import asyncio
    calls = 0
    async def slow(request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return httpx.Response(200, json=CORE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        upstreams = Upstreams(client, SETTINGS)
        with pytest.raises(UpstreamError) as error:
            await asyncio.wait_for(upstreams.get("CORE", SETTINGS.core_url, "timeout-test"), timeout=0.5)
    assert error.value.code == "TIMEOUT"
    assert calls == 2


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"{}"])
def test_invalid_core_payload_degrades_without_retry(body):
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "core.test":
            calls += 1
            return httpx.Response(200, content=body)
        return handler(request)
    with client_for(upstream) as client:
        response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
    assert response.status_code == 200
    assert response.json()["warnings"][0]["code"] == "INVALID_RESPONSE"
    assert calls == 1


def test_reject_mismatched_identity_and_incomplete_carts():
    with pytest.raises(ValueError):
        map_customer(CORE, 2)
    with pytest.raises(ValueError):
        map_products(CARTS, 2)
    with pytest.raises(ValueError):
        map_products({"carts": [], "total": 1}, 1)


def test_decimal_rounding_and_empty_carts():
    assert map_products({"carts": [], "total": 0}, 1).netTotalUsd == Decimal("0.00")
    payload = {"total": 1, "carts": [{"userId": 1, "products": [
        {"id": 1, "title": "A", "price": "0.10", "quantity": 3, "discountPercentage": "5"}]}]}
    assert map_products(payload, 1).netTotalUsd == Decimal("0.29")
