import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger("integrahub")
MAX_RESPONSE_BYTES = 1_000_000


@dataclass
class UpstreamError(Exception):
    code: str


class Upstreams:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.states = {p: "unknown" for p in ("CORE", "PRODUCTS", "FX")}
        if settings.unstable_url:
            self.states["UNSTABLE"] = "unknown"

    async def get(self, provider: str, url: str, request_id: str, *, json_body=True):
        for attempt in range(1, self.settings.max_attempts + 1):
            started = time.perf_counter()
            retry = False
            status = None
            code = "OK"
            try:
                # A total per-attempt deadline also bounds slow-drip responses.
                async with asyncio.timeout(self.settings.timeout_seconds):
                    async with self.client.stream("GET", url, headers={"X-Request-Id": request_id}) as response:
                        status = response.status_code
                        if 500 <= status <= 599:
                            retry, code = True, "UPSTREAM_5XX"
                        elif not 200 <= status <= 299:
                            code = "NOT_FOUND" if status == 404 else "UPSTREAM_HTTP_ERROR"
                        else:
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                body.extend(chunk)
                                if len(body) > MAX_RESPONSE_BYTES:
                                    raise UpstreamError("RESPONSE_TOO_LARGE")
                            if json_body:
                                try:
                                    payload = json.loads(body)
                                except (ValueError, UnicodeError):
                                    raise UpstreamError("INVALID_RESPONSE") from None
                                if not isinstance(payload, dict):
                                    raise UpstreamError("INVALID_RESPONSE")
                            else:
                                payload = {}
                            self.states[provider] = "up"
                            return payload
            except (TimeoutError, httpx.TimeoutException):
                retry, code = True, "TIMEOUT"
            except httpx.RequestError:
                code = "NETWORK_ERROR"
            except UpstreamError as exc:
                code = exc.code
            finally:
                # Never log URLs, headers, customer IDs, provider bodies or exception strings.
                logger.info(json.dumps({"event": "upstream", "provider": provider,
                    "requestId": request_id, "attempt": attempt, "status": status,
                    "result": code, "latencyMs": round((time.perf_counter()-started)*1000, 2)}))
            self.states[provider] = "down"
            if not retry or attempt == self.settings.max_attempts:
                raise UpstreamError(code)
            delay = self.settings.backoff_seconds * 2 ** (attempt-1)
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
