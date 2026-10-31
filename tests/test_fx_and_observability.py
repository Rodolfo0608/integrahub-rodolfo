import asyncio
from dataclasses import replace

import httpx
import pytest

from app.cache import FxCache
from tests.test_integration import CARTS, CORE, FX, KEY, SETTINGS, client_for, handler


def test_fx_conversion_and_one_call_for_two_profiles():
    fx_calls = 0
    def upstream(request):
        nonlocal fx_calls
        if request.url.host == "fx.test":
            fx_calls += 1
        return handler(request)
    with client_for(upstream) as client:
        for _ in range(2):
            response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
            assert response.json()["fx"]["convertedTotals"]["EUR"]["amount"] == "24.30"
            assert response.json()["fx"]["convertedTotals"]["GBP"]["amount"] == "21.60"
    assert fx_calls == 1


@pytest.mark.parametrize("payload", [{"base": "EUR", "date": "2026-10-30", "rates": {"EUR": 1, "GBP": 1}},
    {"base": "USD", "date": "2026-10-30", "rates": {"EUR": 0, "GBP": 1}},
    {"base": "USD", "date": "2026-10-30", "rates": {"EUR": 1}}, {}])
def test_bad_fx_degrades_and_is_not_cached(payload):
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "fx.test":
            calls += 1
            return httpx.Response(200, json=payload)
        return handler(request)
    with client_for(upstream) as client:
        for _ in range(2):
            data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
            assert data["partial"] is True
            assert data["products"]["netTotalUsd"] == "27.00"
            assert data["fx"] is None
            assert data["warnings"][0]["provider"] == "FX"
    assert calls == 2


def test_unstable_500_retries_and_degrades():
    calls = 0
    def upstream(request):
        nonlocal calls
        if request.url.host == "unstable.test":
            calls += 1
            return httpx.Response(500)
        return handler(request)
    settings = replace(SETTINGS, unstable_url="https://unstable.test/status/500")
    with client_for(upstream, settings) as client:
        data = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY}).json()
    assert data["partial"] is True
    assert data["customer"] is not None
    assert data["products"] is not None
    assert data["warnings"][0]["provider"] == "UNSTABLE"
    assert calls == 2


def test_health_reports_last_observation_and_openapi_auth():
    with client_for() as client:
        before = client.get("/health", headers={"X-Api-Key": KEY}).json()
        assert before["status"] == "unknown"
        client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": KEY})
        after = client.get("/health", headers={"X-Api-Key": KEY}).json()
        assert after["status"] == "ok"
        assert after["dependencies"] == {"CORE": "up", "PRODUCTS": "up", "FX": "up"}
        assert after["fxCacheFresh"] is True
        schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/customers/{customer_id}/profile"]["get"]
    assert operation["security"] == [{"APIKeyHeader": []}]


def test_request_id_sanitized_and_logs_have_no_payloads(caplog):
    import logging
    caplog.set_level(logging.INFO, logger="integrahub")
    with client_for() as client:
        response = client.get("/api/v1/customers/1/profile",
                              headers={"X-Api-Key": KEY, "X-Request-Id": "bad id with spaces"})
    rid = response.headers["X-Request-Id"]
    assert rid != "bad id with spaces"
    assert response.json()["requestId"] == rid
    assert rid in caplog.text
    for secret in ("SENSITIVE", "ana@example.test", KEY, "bad id with spaces", "core.test"):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_fx_singleflight_and_expiry():
    cache = FxCache(ttl=0.01)
    calls = 0
    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        return FX
    values = await asyncio.gather(*(cache.get(load) for _ in range(10)))
    assert len(values) == 10
    assert calls == 1
    await asyncio.sleep(0.02)
    await cache.get(load)
    assert calls == 2


@pytest.mark.asyncio
async def test_cancelled_waiter_must_not_reuse_expired_task():
    cache = FxCache(ttl=60)
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0
    async def load():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return FX
    waiter = asyncio.create_task(cache.get(load))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await asyncio.sleep(0.01)
    cache.expires_at = 0
    await cache.get(load)
    assert calls == 2
