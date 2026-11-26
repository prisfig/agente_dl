# Corrección de la selección del lote 2: exclusión de GOLD(PAXG)USDT

**Fecha de la decisión:** 20 de noviembre de 2026, ~02:45 UTC (19 nov, 8:45 pm hora de México), después de la ejecución en
Colab (selección 02:00 UTC) y **antes de revisar cualquier resultado** del activo (métricas de VA o TE, simulación o pronóstico).

## Qué pasó

La regla de la sección 0.4 del notebook, fijada antes de entrenar, excluye los tokens respaldados por oro u otros activos,
porque su precio sigue al activo de respaldo y no es lo que el sistema pretende pronosticar. El filtro se implementó
comparando la base del par contra una lista (`PAXG`, `XAUT`, …). MEXC nombra estos pares `GOLD(PAXG)USDT` y
`GOLD(XAUT)USDT`, con base `GOLD(PAXG)` y `GOLD(XAUT)`, así que el filtro no los reconoció:

- `GOLD(XAUT)USDT` (rango 8 por volumen) quedó fuera de todas formas por tener menos de 1,560 días de velas.
- `GOLD(PAXG)USDT` (rango 14) pasó el filtro y quedó entre los 11 elegidos.

## Qué se decidió

Se excluye `GOLD(PAXG)USDT`: la regla escrita lo excluía y el error fue de implementación. **No se sustituye** por el
siguiente candidato, porque la selección dependía del volumen de 24 h en el momento de la ejecución (20 nov 02:00 UTC) y una
nueva selección usaría otro volumen. El agente queda con 14 activos (4 anteriores + 10 del lote 2) en vez de 15.

Su modelo se entrenó, se evaluó en TE y se verificó como los demás (los archivos se conservan en esta carpeta), pero no se
carga en el agente ni se reporta como activo operado. Los otros diez elegidos cumplen la regla tal como está escrita.

## Activos del lote 2 en el agente (v1.6)

BNBUSDT, ADAUSDT, LTCUSDT, TRXUSDT, DOGEUSDT, MXUSDT, FILUSDT, BCHUSDT, ZECUSDT y NEARUSDT.
