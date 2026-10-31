import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    core_url: str
    products_url: str
    fx_url: str
    unstable_url: str | None = None
    api_key: str = ""
    timeout_seconds: float = 1.5
    max_attempts: int = 2
    backoff_seconds: float = 0.1
    fx_ttl_seconds: float = 3600

    @classmethod
    def from_env(cls):
        settings = cls(
            core_url=os.environ.get("CORE_URL", ""),
            products_url=os.environ.get("PRODUCTS_URL", ""),
            fx_url=os.environ.get("FX_URL", ""),
            unstable_url=os.environ.get("UNSTABLE_URL") or None,
            api_key=os.environ.get("API_KEY", ""),
            timeout_seconds=float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "1.5")),
            max_attempts=int(os.environ.get("UPSTREAM_MAX_ATTEMPTS", "2")),
            backoff_seconds=float(os.environ.get("UPSTREAM_BACKOFF_SECONDS", "0.1")),
            fx_ttl_seconds=float(os.environ.get("FX_TTL_SECONDS", "3600")),
        )
        for name in ("core_url", "products_url", "fx_url", "unstable_url"):
            value = getattr(settings, name)
            if name == "unstable_url" and value is None:
                continue
            if not value or urlparse(value).scheme not in ("http", "https") or not urlparse(value).netloc:
                raise ValueError(f"Configure {name.upper()} con una URL HTTP válida")
        if not settings.api_key or len(settings.api_key) < 16:
            raise ValueError("API_KEY es obligatoria y debe tener al menos 16 caracteres")
        if not 0.05 <= settings.timeout_seconds <= 10:
            raise ValueError("UPSTREAM_TIMEOUT_SECONDS debe estar entre 0.05 y 10")
        if not 1 <= settings.max_attempts <= 3:
            raise ValueError("UPSTREAM_MAX_ATTEMPTS debe estar entre 1 y 3")
        if not 0 <= settings.backoff_seconds <= 2 or not 1 <= settings.fx_ttl_seconds <= 86400:
            raise ValueError("Backoff o TTL fuera de rango")
        return settings
