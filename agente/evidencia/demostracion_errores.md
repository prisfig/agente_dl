# Demostración de los escenarios de error

**Fecha:** 16 de noviembre de 2026, de 18:14 a 18:33 (hora de Ciudad de México; 00:14–00:33 UTC del 17).
**Versión del agente:** v1.1–v1.2 (ver `CHANGELOG.md`). **Equipo:** MacBook Air M1, 8 GB, Ollama 0.40.16 con `llama3.2:3b`.

La demostración se hizo con una **instancia separada** del agente (`AGENTE_CONFIG=config/demo/…`), con bases de datos propias
(`demo_errores.sqlite3`, `demo_json.sqlite3`, `demo_saldo.sqlite3`), para no alterar los ciclos en vivo que se reportan en la evaluación.
Cada error se provocó con un fallo real (Ollama cerrado, Wi‑Fi apagado, clave equivocada, límite real de tokens, etc.), no con datos simulados.

Exportaciones: `demo_errores_eventos.csv` (bitácora completa de las tres bases) y `demo_errores_ordenes.csv` (órdenes Paper).

## Resultados

| # | Escenario del protocolo | Cómo se provocó | Respuesta del sistema | Evento en la bitácora | ¿Operación indebida? |
|---|---|---|---|---|---|
| 1 | Ollama detenido | Se cerró la app de Ollama y se pidió un ciclo | 3 intentos con espera creciente (2 s, 4 s); el gateway respondió 502; el agente pasó a **pausado** | `llm_no_disponible` — 18:15:54 (demo_errores #3) | No. Sin órdenes; la vela no se marcó como procesada |
| 2 | API de MEXC sin respuesta | Wi‑Fi apagado y ciclo pedido | 3 intentos con espera creciente; error de conexión; agente **pausado** | `sin_respuesta` — 18:18:02 (demo_errores #5) | No |
| 3 | Evento duplicado | Se pidió dos veces el ciclo de la vela 2026‑11‑16 | El primero se completó (27 s); el segundo se rechazó sin repetir operaciones | `evento_duplicado` — 18:20:20 (demo_errores #8) | No. Siguieron 2 órdenes, no 4 |
| 4 | Reinicio del backend | `Ctrl + C` y nuevo arranque | Estado, carteras y posiciones recuperados de SQLite; un nuevo ciclo de la misma vela se rechazó como duplicado | `arranque` (#9) y `evento_duplicado` — 18:22:50 (#10) | No |
| 5 | Clave incorrecta (API privada) | `curl` con clave equivocada y sin clave, incluido un intento de **iniciar** el agente | HTTP 401 en ambos; el agente siguió **detenido** | `clave_incorrecta` ×2 — 18:27:11 (demo_errores #13, #14) | No |
| 6 | Botón de detención | Botón **Detener** en la interfaz | Agente **detenido**; nuevas órdenes bloqueadas; las posiciones se conservaron. Liquidar se ejecutó después como acción aparte | `control` — 18:25:01 (#11) y liquidación 18:25:35 (#12) | No. Detener no liquidó; la venta solo ocurrió al pulsar Liquidar |
| 7 | Clave incorrecta (gateway del LLM) | Backend arrancado con `GATEWAY_API_KEY` equivocada | El gateway rechazó con 401; sin reintentos inútiles; agente **pausado** | `clave_incorrecta` — 18:29:14 (demo_json #3) | No |
| 8 | JSON inválido | Ollama limitado a 6 tokens en la respuesta final (`num_predict`) | Respuesta cortada `{"accion": "COMPR`; 3 intentos; agente **pausado** | `json_invalido` — 18:30:51 (demo_json #6), con la respuesta cruda guardada | No |
| 9 | Dato atrasado | Antigüedad máxima reducida a 0.05 h (3 min) | La vela 2026‑11‑16 tenía 0.5 h; se rechazó antes de decidir; agente **pausado** | `dato_atrasado` — 18:31:46 (demo_errores #17) | No |
| 10 | Saldo insuficiente | Capital de 0.50 USDT, menor que el monto mínimo del par (1 USDT) | El ciclo se completó; las compras de *con LLM* y *comprar y mantener* se rechazaron y la acción final quedó en MANTENER | `saldo_insuficiente` ×2 — 18:32:33 (demo_saldo #3, #4) | No. Órdenes registradas como `rechazada` |

El **límite de solicitudes** de MEXC (HTTP 429) no se puede provocar a voluntad contra el servidor real; está cubierto por la prueba
automatizada `test_mexc_limite_de_solicitudes_reintenta_con_espera_creciente_y_falla` (dos esperas de 1 s y 2 s, luego error
`limite_solicitudes` y pausa).

## Comportamiento común

- **Mensaje útil:** cada error se muestra en la interfaz y en Auditoría con su causa (p. ej., "Ollama no está disponible (¿está detenido?)").
- **Registro:** todos quedan en la tabla `eventos` con fecha, nivel, tipo, mensaje y detalle (intentos, respuesta cruda del LLM).
- **Reintentos limitados con espera creciente** y, al fallar, **pausa de nuevas decisiones** hasta que el usuario vuelve a iniciar.
- **Sin operaciones indebidas:** ningún error produjo órdenes; la vela afectada no se marca como procesada y puede reintentarse.

## Pruebas automatizadas equivalentes

`cd agente/backend && python -m pytest` (44 pruebas). Los escenarios anteriores también se verifican en
`tests/test_agente.py` (`test_error_1` … `test_error_9`) y `tests/test_mexc_llm_gateway.py`.
