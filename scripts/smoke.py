"""Smoke test against an already-running local server; never prints the API key or PII."""
import argparse
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("API_KEY")
if not key:
    raise SystemExit("Configura primero API_KEY en .env")
with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=15) as client:
    response = client.get("/api/v1/customers/1/profile", headers={"X-Api-Key": key, "X-Request-Id": "smoke-local"})
    response.raise_for_status()
    data = response.json()
    assert response.status_code == 200
    assert data["requestId"] == response.headers["X-Request-Id"] == "smoke-local"
    assert client.get("/api/v1/customers/1/profile").status_code == 401
    assert all(word not in response.text for word in ('"password"', '"ssn"', '"bank"', '"crypto"'))
    print(json.dumps({"httpStatus": response.status_code, "partial": data["partial"],
                      "sections": {field: data[field] is not None for field in ("customer", "products", "fx")},
                      "warningCodes": [w["code"] for w in data["warnings"]],
                      "authentication": "401 sin clave", "trace": "OK"}, indent=2))
