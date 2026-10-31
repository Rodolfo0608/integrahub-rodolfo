# IntegraHub

Servicio HTTP que agrega el perfil de un cliente desde CORE, PRODUCTOS y FX. Usa **Python 3.12+, FastAPI y httpx**. Ante fallas de un proveedor conserva las secciones disponibles, responde HTTP 200 y declara `partial: true` y `warnings[]`.

## Ejecutar en menos de 5 minutos

Prerrequisitos: Python 3.12 o superior, pip, Git y acceso a Internet para instalar dependencias y consultar proveedores. No requiere base de datos, frontend, Docker ni claves de APIs externas.

### Windows / PowerShell

```powershell
git clone https://github.com/rodolfo0608/integrahub-rodolfo.git
cd integrahub-rodolfo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
Copy-Item .env.example .env
# Genera una clave local aleatoria. Si ya tienes una .env propia, conserva tu configuración.
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('replace-with-a-random-local-key',secrets.token_urlsafe(32)))"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

Si tu instalación usa el lanzador de Python, sustituye el primer `python` por `py -3`. También se incluye `./run-local.ps1`: crea el entorno, instala dependencias de desarrollo, genera `.env` solo si no existe y arranca el servicio. Puede localizar el Python incluido con Codex si está disponible, o aceptar su ruta mediante `INTEGRAHUB_PYTHON`. No cambia la política de ejecución de PowerShell.

### Linux / macOS

```bash
git clone https://github.com/rodolfo0608/integrahub-rodolfo.git
cd integrahub-rodolfo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c constraints.txt
cp .env.example .env
.venv/bin/python -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('replace-with-a-random-local-key',secrets.token_urlsafe(32)))"
.venv/bin/python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

### Llamar al endpoint

En otra terminal, copia el valor de `API_KEY` de tu `.env`. No lo publiques. En Windows usa `curl.exe` para evitar el alias de Windows PowerShell:

```bash
curl -i http://127.0.0.1:8000/api/v1/customers/1/profile -H "X-Api-Key: TU_CLAVE_LOCAL" -H "X-Request-Id: demo-001"
curl -i http://127.0.0.1:8000/health -H "X-Api-Key: TU_CLAVE_LOCAL"
```

Sin clave o con clave inválida: HTTP 401. ID que no sea entero positivo o supere 2147483647: HTTP 422. Un 404 del proveedor se representa mediante advertencia y sección `null`, sin reintentos y con HTTP 200, conforme a la política de degradación. Incluso si fallan todos los proveedores, la respuesta es 200 con `partial: true`; no es una garantía de que el cliente exista.

Swagger UI: `http://127.0.0.1:8000/docs`, botón **Authorize**, API key. Contrato generado: `/openapi.json`. Esas rutas solo exponen el esquema y no requieren clave. El perfil y `/health` sí requieren clave.

Prueba rápida sin imprimir la clave ni información personal:

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py
# Si el puerto 8000 está ocupado, arranca con --port 8001 y prueba:
.\.venv\Scripts\python.exe scripts/smoke.py --port 8001
```

## Contrato canónico

Ejemplo ilustrativo, coherente con los fixtures de pruebas. Los proveedores reales contienen otros nombres, importes y fechas.

```json
{
  "customerId": 1,
  "customer": {
    "id": 1,
    "fullName": "Ana Pérez",
    "email": "ana@example.test",
    "phone": "+50700000000",
    "address": {"street": "Calle 1", "city": "Panamá", "country": "Panamá"}
  },
  "products": {
    "cartCount": 1,
    "itemCount": 1,
    "units": 3,
    "items": [{"id": 10, "name": "Producto", "quantity": 3,
      "unitPriceUsd": "10.00", "grossTotalUsd": "30.00",
      "discountPercent": "10", "netTotalUsd": "27.00"}],
    "grossTotalUsd": "30.00",
    "discountTotalUsd": "3.00",
    "netTotalUsd": "27.00"
  },
  "fx": {
    "base": "USD", "date": "2026-10-30",
    "convertedTotals": {
      "EUR": {"rate": "0.9", "amount": "24.30"},
      "GBP": {"rate": "0.8", "amount": "21.60"}
    }
  },
  "partial": false,
  "warnings": [],
  "requestId": "demo-001"
}
```

- `customer`, `products` o `fx` son `null` cuando no se pueden construir. Una lista vacía de carritos válida devuelve totales cero; una falla de PRODUCTOS devuelve `products: null`, sin inventar ceros.
- Nombre completo = nombre + apellido; dirección = calle, ciudad y país. Lista permitida explícita: no se devuelve `password`, `ssn`, `bank`, `crypto` ni campos adicionales del proveedor. El modelo de salida también prohíbe campos no declarados.
- `itemCount` cuenta líneas; `units` suma cantidades. Si un producto aparece en varios carritos, se conservan las líneas por separado. Se exige que el cliente/propietario del carrito coincida con el ID solicitado. `limit=0` solicita todos los carritos; si `total` difiere de los recibidos se rechaza la sección incompleta.
- Dinero: `Decimal`, cadenas JSON y redondeo `ROUND_HALF_UP` a dos decimales por línea. Bruto = precio × cantidad; neto = bruto × (1 − descuento/100); totales = suma de líneas. Se ignoran los agregados y totales upstream. EUR/GBP se calculan sobre el neto USD y se incluyen fecha y tasa. FX no implica conversión contable ni fecha de transacción.

Ejemplo de degradación si PRODUCTOS devuelve 500:

```json
{"provider": "PRODUCTS", "code": "UPSTREAM_5XX", "message": "Proveedor no disponible; sección omitida."}
```

Se conserva `customer`, `products` y `fx` quedan `null`, `partial` es `true` y esa advertencia aparece en `warnings`. Los errores nunca incluyen cuerpos, URLs ni excepciones crudas del proveedor.

## Decisiones técnicas

- **Separación:** `config.py` configura; `upstreams.py` maneja HTTP y resiliencia; `mapping.py` valida contratos externos y normaliza; `models.py` define la salida; `main.py` autentica y orquesta. CORE, PRODUCTOS, FX y el INESTABLE opcional se ejecutan en paralelo con `asyncio.gather`, reutilizando un único cliente HTTP por proceso.
- **Resiliencia acotada:** plazo total por intento de 1.5 s con `asyncio.timeout`, más los timeouts de httpx. Dos intentos como máximo: el segundo solo ante 5xx o timeout, con backoff exponencial de 100 ms y jitter de hasta 20%. Nunca reintenta 4xx (incluido 429), errores de contrato, red ni redirecciones. Presupuesto upstream predeterminado por llamada lógica: aproximadamente 3.12 s; no es un SLA global bajo saturación. El body se limita a 1 MB y no se siguen redirecciones automáticamente.
- **FX y fallas:** TTL de una hora con reloj monotónico y una sola carga concurrente compartida por proceso. Solo se cachean tasas válidas; no se sirven tasas vencidas y los fallos se informan manteniendo USD. INESTABLE es una demostración opcional; su circuit breaker abre tras tres llamadas lógicas fallidas, espera 30 s y admite una sola prueba en half-open. Sus fallas no eliminan datos de CORE/PRODUCTOS.
- **Seguridad y observabilidad:** API key de entorno comparada en tiempo constante; configuración ausente o inválida impide arrancar. Request ID aceptado solo si contiene 1–64 caracteres alfanuméricos, punto, guion o guion bajo; en otro caso se genera UUID. Se devuelve en JSON/header y se propaga a cada llamada real. Logs JSON con proveedor, intento, estado y latencia; sin payloads, IDs de cliente, correos, URLs o secretos. `--no-access-log` evita que Uvicorn registre IDs de cliente desde la ruta; httpx tampoco registra URLs.

## Configuración

Todas las URLs y secretos se leen de variables de entorno; sus ejemplos están únicamente en `.env.example`. Los cambios requieren reiniciar el proceso. `.env` y los entornos virtuales están ignorados por Git.

| Variable | Valor de ejemplo / función |
|---|---|
| `API_KEY` | Clave propia de al menos 16 caracteres |
| `CORE_URL` | Plantilla de usuario con `{id}` |
| `PRODUCTS_URL` | Plantilla de carritos con `{id}` y `limit=0` |
| `FX_URL` | Tasas USD → EUR, GBP |
| `UNSTABLE_URL` | Vacío desactiva la demostración |
| `UPSTREAM_TIMEOUT_SECONDS` | `1.5`, rango permitido 0.05–10 |
| `UPSTREAM_MAX_ATTEMPTS` | `2`, incluye intento inicial, rango 1–3 |
| `UPSTREAM_BACKOFF_SECONDS` | `0.1`, rango 0–2, más jitter hasta 20% |
| `FX_TTL_SECONDS` | `3600`, rango 1–86400 |

El PDF muestra el dominio `api.frankfurter.dev` dividido entre líneas; la configuración usa su URL completa `https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP`, comprobada directamente. Ningún proveedor exige API key.

## Demostrar fallas

En `.env`, establece `UNSTABLE_URL` con uno de los ejemplos comentados:

1. `https://httpbin.org/status/500`: dos intentos, warning `UPSTREAM_5XX`.
2. `https://httpbin.org/delay/6`: plazo de 1.5 s por intento, warning `TIMEOUT` si realmente tarda 6 s. El comportamiento público puede variar; los tests controlados demuestran la política de forma determinista.

Reinicia el servicio después de cada cambio. Tres solicitudes con fallas abren el breaker; la cuarta devuelve `CIRCUIT_OPEN` sin llamar INESTABLE. Después de 30 s se permite una prueba. Restablecer `UNSTABLE_URL=` deshabilita la demo. CORE/PRODUCTOS/FX se mantienen con sus URLs reales; no se usan stubs por defecto.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -c constraints.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

En Linux/macOS sustituye el ejecutable por `.venv/bin/python`. Los tests usan `httpx.MockTransport`, sin depender de Internet; verifican mapeo, dinero, filtrado sensible, identidad, errores 4xx/5xx, timeout total con respuesta lenta, backoff, recuperación, concurrencia, caché TTL/cancelación, breaker, autenticación, trazabilidad, logs y OpenAPI. Hay un workflow de GitHub Actions para Python 3.12.

## Alcance y limitaciones

- Caché, estados y breaker viven en memoria por proceso; no se comparten entre workers y se pierden al reiniciar. No hay rate limiting, caché negativa FX ni protección global frente a saturación. El pool está limitado a 100 conexiones.
- `/health` requiere API key y devuelve HTTP 200 como diagnóstico. Informa la **última observación** por dependencia, no sondeo activo ni garantía de disponibilidad actual. Al arrancar: `unknown`. La caché FX indica frescura por separado.
- Validar el contrato detecta campos requeridos ausentes o tipos inválidos en la llamada; no hay alertas proactivas por cambios upstream, métricas exportadas ni trazas distribuidas.
- HTTP local se limita a loopback. TLS, rotación de claves, permisos por cliente y gestión corporativa de secretos corresponden a un despliegue posterior.
- Los tests actuales emiten una advertencia de deprecación de Starlette por el uso de `httpx` en su TestClient. Pasan con las versiones fijadas; una migración futura a `httpx2` requeriría verificar el transporte de pruebas.
- No se ha realizado una prueba de carga ni un despliegue productivo. El workflow CI se ejecutó con éxito para `07a1109` en Ubuntu/Python 3.12: [ejecución verificada](https://github.com/Rodolfo0608/integrahub-rodolfo/actions/runs/41214719648).

Ver `STATUS.md` para evidencia y `AI-LOG.md` para participación de IA y correcciones reales.
