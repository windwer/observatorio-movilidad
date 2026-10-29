# Evidencia de QA · 29/10/2026

- `runtime.json`: ensayo funcional HTTP con datos reales, cuatro operadores,
  población, geometrías, cola, cancelación y reutilización. Se ejecutó antes
  de la última corrección del caso sin precálculo.
- `load-before-cold-stop-fix.json`: carga que detectó 17 esperas agotadas.
  Es un resultado fallido conservado para trazabilidad; no representa una
  aprobación de rendimiento. La repetición posterior está bloqueada por el
  límite de uso de herramientas.
- `dependencies.json`: auditoría de dependencias, sin vulnerabilidades
  conocidas encontradas en esa consulta.

Batería completa: 104 pruebas sin fallos, 3 DEMO omitidas. Comprobación posterior:
34 pruebas sin fallos, con 1 prueba asíncrona omitida por restricción del entorno.
Trabajador: una prueba adicional con procesos reales pasó tras incorporar el
rechazo de trabajos creados para otros datos. Interfaz Node: 7 pruebas pasadas.
Docker/Caddy no se ejecutó en este equipo.

Informe y límites: [VALIDACION_V1.3.0.md](../../VALIDACION_V1.3.0.md).
