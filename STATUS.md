# Estado de la entrega

Inicio declarado: **31 de octubre de 2026, 09:54, Panamá (UTC-5)**. Límite de 2 h 15 min: **12:09**. Las horas se conservan en los commits reales; no se retrofecharon.

| Requisito | Estado | Evidencia / nota |
|---|---|---|
| P0: esqueleto caminante y commit antes del minuto 30 | Hecho | `6e1caf2`, 10:08:04 UTC-5, minuto 14. Se levantó Uvicorn y se comprobó HTTP 200 por la interfaz HTTP real antes del commit. |
| P0: contrato canónico y filtro sensible | Hecho | Modelos propios en `models.py`, mapeo explícito en `mapping.py`, JSON y semántica en README. Tests con marcadores de password, ssn, tarjeta y wallet. |
| P0: CORE + PRODUCTOS reales | Hecho | Concurrencia con `asyncio.gather`. Verificados ambos con APIs reales. Identidad del cliente validada. Totales recalculados con Decimal, sin confiar en agregados upstream. |
| P0: timeout y reintentos con backoff | Hecho | Plazo total por intento + httpx, máximo dos intentos por defecto, backoff exponencial con jitter. Solo reintenta 5xx y timeout. Tests de 401/404/429 sin reintento y de cuerpo lento. |
| P0: degradación elegante | Hecho | HTTP 200, secciones `null`, `partial` y warnings. Tests con CORE/PRODUCTOS fallando por separado y todos fallando; errores de contrato no exponen contenido. |
| P1: autenticación de entorno | Hecho | `X-Api-Key`, comparación en tiempo constante, 401 antes de llamar proveedores. Sin clave configurada no arranca. `.env` ignorado. |
| P1: caché FX con TTL | Hecho | En memoria por proceso, 1 h por defecto; carga compartida, validación antes de cachear, expiración y cancelaciones probadas. No sirve valores vencidos. |
| P1: request ID | Hecho | Recibido o UUID, saneado, presente en respuesta JSON/header, propagado en llamadas upstream y logs. |
| P1: logs estructurados | Hecho | JSON por intento con proveedor, latencia, resultado, estado e ID de solicitud; sin payloads, secretos, URLs ni IDs de cliente. |
| P2: pruebas con proveedores simulados | Hecho | 47 casos con MockTransport en el momento de la validación final. No requieren Internet. |
| P2: GET /health por dependencia | Hecho | Endpoint protegido; última observación en este proceso, estado inicial unknown, frescura FX y estado del breaker. No sondeo activo. |
| P2: circuit breaker INESTABLE | Hecho | Abre tras 3 llamadas lógicas fallidas; cooldown 30 s; una prueba half-open. Tests de apertura, rechazo, recuperación y cancelación de la prueba. |
| P2: OpenAPI | Hecho | `/openapi.json` y `/docs` generados por FastAPI, modelo de respuesta y esquema API key; comprobados en tests. |
| README, AI-LOG, .env.example | Hecho | Instrucciones Windows/Linux, contrato, decisiones, limitaciones, prompts y corrección real de código de IA. |
| Repositorio público con historial progresivo | Hecho | El candidato ejecutó el push desde PowerShell normal. Publicación comprobada: la rama main remota coincidió con `07a1109`; conserva los cinco commits progresivos y el esqueleto temprano. |
| CI en GitHub | Hecho | GitHub Actions terminó con success para `07a1109` en Ubuntu/Python 3.12. [Ejecución verificada](https://github.com/Rodolfo0608/integrahub-rodolfo/actions/runs/41214719648). Los cambios posteriores de cierre son de documentación; su nueva ejecución debe comprobarse al publicar. |

## Evidencia de ejecución

- `python -m pytest -q`: **47 passed, 1 warning**, en aproximadamente 2 s. Repetido en un entorno nuevo creado con `run-local.ps1 -SetupOnly`.
- `python -m pip check`: **No broken requirements found**.
- HTTP real a servidor local: perfil 200 con las tres secciones y sin warnings; solicitud sin API key 401; health con CORE/PRODUCTS/FX `up`.
- Proveedores reales: ejecución normal 200 completo (~1.03 s); INESTABLE 500 con datos conservados (~1.85 s); INESTABLE delay/6 con TIMEOUT y datos conservados (~3.12 s). Son observaciones puntuales, no resultados de carga ni garantías de latencia.
- Advertencia conocida: deprecación del TestClient de Starlette con httpx. No se ocultó ni se convirtió en prueba fallida. Versiones de validación fijadas en `requirements*.txt` y `constraints.txt`.
- Sin stubs en el modo predeterminado. Los stubs se usan únicamente en tests deterministas.

## Fuera del alcance de producción

No se hicieron pruebas de carga, despliegue productivo, rate limiting, caché/breaker distribuidos, telemetría exportada, alertas por drift de contrato ni rotación corporativa de secretos. Para escalar: medir concurrencia, introducir límites de admisión, métricas y caché distribuida antes de aumentar workers. No se declara cobertura del 100%.
