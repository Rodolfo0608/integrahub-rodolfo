# IntegraHub

Python + FastAPI. Servicio de agregación de perfil de cliente.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/api/v1/customers/1/profile
```

Esqueleto inicial: datos fijos, integración pendiente.
