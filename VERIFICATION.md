# Verificación reproducible

Validación local el 31 de octubre de 2026, dentro de la ventana de la prueba. Python 3.12 en Windows. Los resultados no incluyen datos personales ni claves.

## Pruebas deterministas

```text
python -m pytest -q
47 passed, 1 warning

python -m pip check
No broken requirements found.
```

La advertencia proviene de TestClient de Starlette: su compatibilidad con httpx está deprecada. El comportamiento probado funciona con el conjunto fijado en constraints.txt. Las pruebas no usan APIs públicas.

## HTTP real al proceso Uvicorn

```json
{"status":200,"partial":false,"customer_present":true,"products_present":true,"fx_present":true,"warnings":[],"request_id":"real-smoke-1"}
```

Sin clave: 401. `/health`: estado ok, CORE/PRODUCTS/FX up y caché FX fresca. Se usó el puerto 8001 porque el puerto 8000 estaba ocupado por el esqueleto inicial.

## Integración real mediante la aplicación ASGI

Las solicitudes a IntegraHub se hicieron con TestClient; sus clientes httpx llamaron realmente a DummyJSON, Frankfurter y httpbin, sin MockTransport. Cada escenario arrancó con caché vacía. El ID fue 1 y los request IDs no contenían datos personales.

| Escenario | HTTP de IntegraHub | partial | Cliente / productos / FX | Advertencia | Tiempo observado |
|---|---|---|---|---|---|
| Normal | 200 | false | Presentes | Ninguna | 1.027 s |
| INESTABLE status/500 | 200 | true | Presentes | UPSTREAM_5XX | 1.854 s |
| INESTABLE delay/6 | 200 | true | Presentes | TIMEOUT | 3.124 s |

En status/500 se observaron dos intentos con estado 500. En delay/6 se observaron dos timeouts cercanos a 1.5 s cada uno, más el backoff. Los logs registraron proveedor, intento, resultado, latencia e ID de solicitud, sin bodies ni URLs.

Estas son comprobaciones puntuales de integración, no un benchmark ni una prueba de carga. `/health` indica última observación; no comprueba activamente cada proveedor al consultarlo.

## GitHub

Repositorio público y rama main comprobados mediante Git y la API pública de GitHub. CI en Ubuntu/Python 3.12: **completed / success** para `07a1109b18930ab0203a834cb924ca3087c38076`. [Ver ejecución](https://github.com/Rodolfo0608/integrahub-rodolfo/actions/runs/41214719648).

La publicación la ejecutó el candidato desde PowerShell normal porque el entorno aislado no pudo invocar el gestor de credenciales. No se accedió a sus contraseñas ni tokens.

## Repetir

1. Instalar y arrancar según README.
2. Ejecutar `python scripts/smoke.py` con el Python del entorno y el puerto correcto.
3. Activar uno de los ejemplos de `UNSTABLE_URL` en `.env` y reiniciar.
4. Repetir el smoke: debe seguir siendo 200 y declarar las advertencias reales. La disponibilidad de APIs públicas puede cambiar.
