import asyncio
import hmac
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.security import APIKeyHeader
from pydantic import ValidationError

from app.cache import FxCache
from app.breaker import CircuitBreaker
from app.config import Settings
from app.mapping import map_customer, map_fx, map_products
from app.models import Profile, Warning
from app.upstreams import UpstreamError, Upstreams

logger = logging.getLogger("integrahub")
logging.basicConfig(level=logging.INFO, format="%(message)s")
# httpx's request logs include full URLs and customer IDs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.from_env()
        async with httpx.AsyncClient(transport=transport, follow_redirects=False,
                                    timeout=app.state.settings.timeout_seconds,
                                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)) as client:
            app.state.upstreams = Upstreams(client, app.state.settings)
            app.state.fx_cache = FxCache(app.state.settings.fx_ttl_seconds)
            app.state.unstable_breaker = CircuitBreaker()
            try:
                yield
            finally:
                await app.state.fx_cache.aclose()

    app = FastAPI(title="IntegraHub", version="1.0.0", lifespan=lifespan,
                  description="Perfil canónico, integración concurrente y degradación por proveedor.")

    @app.middleware("http")
    async def trace(request: Request, call_next):
        supplied = request.headers.get("X-Request-Id", "")
        request.state.request_id = supplied if REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        logger.info(json.dumps({"event": "request", "requestId": request.state.request_id,
            "status": response.status_code, "latencyMs": round((time.perf_counter()-started)*1000, 2)}))
        return response

    async def authenticate(request: Request, x_api_key: Annotated[str | None, Depends(api_key_header)] = None):
        if x_api_key is None or not hmac.compare_digest(
                x_api_key.encode(), request.app.state.settings.api_key.encode()):
            raise HTTPException(status_code=401, detail="Missing or invalid API key")

    @app.get("/api/v1/customers/{customer_id}/profile", response_model=Profile,
             dependencies=[Depends(authenticate)],
             responses={401: {"description": "API key ausente o inválida"},
                        422: {"description": "ID inválido"}})
    async def profile(request: Request, customer_id: Annotated[int, Path(gt=0, le=2147483647)]):
        upstreams = request.app.state.upstreams
        config = request.app.state.settings
        rid = request.state.request_id
        warnings = []

        async def fetch_and_map(provider, url, mapper):
            try:
                payload = await upstreams.get(provider, url, rid)
                return mapper(payload, customer_id)
            except UpstreamError as exc:
                warnings.append(Warning(provider=provider, code=exc.code,
                                        message="Proveedor no disponible; sección omitida."))
            except (ValidationError, ValueError, ArithmeticError):
                upstreams.states[provider] = "invalid_response"
                logger.warning(json.dumps({"event": "mapping", "provider": provider,
                                           "requestId": rid, "result": "INVALID_RESPONSE"}))
                warnings.append(Warning(provider=provider, code="INVALID_RESPONSE",
                                        message="Respuesta incompatible con el contrato esperado."))
            return None

        async def fetch_fx():
            try:
                return await request.app.state.fx_cache.get(lambda: upstreams.get("FX", config.fx_url, rid))
            except UpstreamError as exc:
                warnings.append(Warning(provider="FX", code=exc.code,
                                        message="Tasas no disponibles; se conservan importes USD."))
            except (ValidationError, ValueError, ArithmeticError):
                upstreams.states["FX"] = "invalid_response"
                logger.warning(json.dumps({"event": "mapping", "provider": "FX",
                                           "requestId": rid, "result": "INVALID_RESPONSE"}))
                warnings.append(Warning(provider="FX", code="INVALID_RESPONSE",
                                        message="Tasas incompatibles; se conservan importes USD."))
            return None

        async def fetch_unstable():
            if config.unstable_url:
                try:
                    await request.app.state.unstable_breaker.call(
                        lambda: upstreams.get("UNSTABLE", config.unstable_url, rid, json_body=False))
                except UpstreamError as exc:
                    if exc.code == "CIRCUIT_OPEN":
                        logger.info(json.dumps({"event": "circuit", "provider": "UNSTABLE",
                                               "requestId": rid, "result": "CIRCUIT_OPEN"}))
                    warnings.append(Warning(provider="UNSTABLE", code=exc.code,
                                            message="Proveedor de demostración no disponible."))

        customer, products, rates, _ = await asyncio.gather(
            fetch_and_map("CORE", config.core_url.replace("{id}", str(customer_id)), map_customer),
            fetch_and_map("PRODUCTS", config.products_url.replace("{id}", str(customer_id)), map_products),
            fetch_fx(), fetch_unstable(),
        )
        fx = None
        if rates is not None and products is not None:
            try:
                fx = map_fx(rates, products.netTotalUsd)
            except (ValidationError, ValueError, ArithmeticError):
                warnings.append(Warning(provider="FX", code="INVALID_RESPONSE",
                                        message="No fue posible convertir los importes USD."))
        warnings.sort(key=lambda w: (w.provider, w.code))
        return Profile(customerId=customer_id, customer=customer, products=products,
                       fx=fx, partial=bool(warnings), warnings=warnings, requestId=rid)

    @app.get("/health", dependencies=[Depends(authenticate)])
    async def health(request: Request):
        states = dict(request.app.state.upstreams.states)
        status = ("degraded" if any(s in ("down", "invalid_response") for s in states.values())
                  else "unknown" if "unknown" in states.values() else "ok")
        cache = request.app.state.fx_cache
        return {"status": status, "dependencies": states,
                "observation": "last_call_in_this_process; not an active probe",
                "fxCacheFresh": cache.value is not None and time.monotonic() < cache.expires_at,
                "unstableCircuit": request.app.state.unstable_breaker.state if request.app.state.settings.unstable_url else "disabled"}

    return app


app = create_app()
