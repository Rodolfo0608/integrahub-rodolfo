# Bitácora de uso de IA

## Herramienta y participación

Codex en la aplicación de escritorio. El candidato solicitó apoyo integral y confirmó las decisiones de lenguaje, identidad de Git y hora de inicio. La IA realiza la mayor parte de la implementación y las comprobaciones; no se presenta como código escrito manualmente por el candidato.

Inicio de la prueba declarado por el candidato: 2026-10-31 09:54, Panamá (UTC-5). Límite: 12:09.

## Stack

Python + FastAPI + httpx. Se creó brevemente un proyecto vacío ASP.NET Core después de que el candidato seleccionara C#, pero antes de integrar aclaró: «La verdad domino más Python pero no lo tengo instalado, tengo es Visual Studio instalado y no se si perderé tiempo con Python». Se cambió a Python porque el entorno de Codex ya ofrece Python 3.12 y porque es el lenguaje que domina mejor. El proyecto C# se retiró del entregable sin usarse como base.

FastAPI aporta validación y OpenAPI; httpx permite I/O asíncrono, transporte simulado y timeouts. Sin base de datos ni frontend. No se clonó una solución de integración ni un boilerplate resuelto.

## Prompts representativos exactos

1. «Recibí esta prueba de Credicorp Bank Panamá como paso final para la contratación, necesito tu apoyo en todo para avanzar y dejar todo listo en base a las instrucciones, revisa e indícame paso a paso para sacar adelante el proyecto lo mejor posible, ya está corriendo las 2 horas desde hace 5 minutos».
   - Resultado: lectura del PDF, identificación de los cinco P0, regla del commit anterior al minuto 30 y planificación de cortes verticales. Se priorizó el endpoint antes de las integraciones.
2. «La verdad domino más Python pero no lo tengo instalado, tengo es Visual Studio instalado y no se si perderé tiempo con Python».
   - Resultado: comprobación del intérprete disponible, instalación de dependencias en un entorno aislado y cambio temprano de stack.

## Contrato canónico

Lista explícita de campos: identidad, nombre, correo, teléfono y dirección; productos con precios y agregados recalculados; conversión EUR/GBP y fecha de tasas. Se descartan password, ssn, bank, crypto y todos los campos no enumerados. Nunca se devuelve un payload upstream completo. Los importes usan Decimal y se serializan como cadenas decimales para evitar pérdida de precisión; redondeo HALF_UP a dos decimales por línea.

## Correcciones y revisión del output

Pendiente de completar con los errores realmente encontrados y sus pruebas. No se inventará una intervención manual del candidato ni una corrección inexistente para satisfacer este apartado.

## Estimación honesta

Estimación preliminar: prácticamente todo el código fue generado por IA; el candidato aportó objetivos, información del entorno y decisiones de stack. La revisión final del candidato debe registrarse solo si realmente se realiza.

## Fortalezas y fallos observados

- Acierto: detectó que el examen permite IA y que la prioridad obligatoria es un endpoint operativo con commit temprano.
- Error: intentó abrir el PDF con `pymupdf`, que no estaba instalado; se corrigió usando `pypdf`, disponible en el runtime. Esto es un error de herramienta, no se cuenta como la corrección de código de integración exigida.

## Verificación y alcance

En progreso. Los resultados definitivos se registrarán después de ejecutar las pruebas, sin atribuir éxito a comprobaciones pendientes.
