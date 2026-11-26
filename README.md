# Deep Learning para Finanzas — práctica y agente de IA financiero

Este repositorio reúne la **práctica** del curso, con el modelo de pronóstico de BTC/USDT, y el **proyecto final**: un agente de IA que opera en **modo Paper** (dinero virtual) con 15 pares de MEXC. El agente combina el modelo LSTM de cada activo, un LLM local (Ollama), controles de riesgo deterministas y una interfaz web.

> El agente **no envía órdenes reales**. Solo lee datos públicos de MEXC y ejecuta las compras y ventas en un simulador propio. Las claves no están en el repositorio.

**Informe del proyecto final:** [`INFORME.md`](INFORME.md) (o en PDF: [`INFORME.pdf`](INFORME.pdf)).

---

## Resultados en vivo (15 activos, datos al 25 nov 2026)

Cada activo tiene tres carteras de 50,000 USDT con el mismo periodo y costos:

| Cartera | Rendimiento neto | Drawdown máx. | Órdenes | Win Rate |
|---|---|---|---|---|
| Sin LLM (estrategia del modelo + riesgo) | **+0.26 %** | −0.93 % | 13 | 80 % (4 de 5) |
| Con LLM (propuesta del LLM + el mismo riesgo) | **−5.70 %** | −7.47 % | 32 | 0 % (0 de 9) |
| Comprar y mantener | **−4.41 %** | −7.04 % | 15 | — |

En este periodo el LLM no aportó valor:
- Nunca propuso vender.
- Propuso comprar sin señal del modelo en 20 de 114 ciclos.
- Todas sus salidas fueron por stop.

El motor de riesgo lo contuvo: rechazó 18 acciones no permitidas y forzó 9 ventas por stop. El detalle por activo y el análisis de las justificaciones del LLM están en el [informe](INFORME.md).

---

## Cómo funciona el agente

```
React + TypeScript (5173) ──X-API-Key──▶ Backend FastAPI (127.0.0.1:8000)
     ├─ MEXC API pública: velas diarias (solo lectura; sin rutas de órdenes reales)
     ├─ Un agente por activo: ensamble de 3 LSTM + escaladores versionados
     ├─ Gateway propio (8001) ──X-API-Key──▶ Ollama local (llama3.2:3b)
     ├─ Motor de riesgo determinista (el LLM no puede saltarlo)
     ├─ Simulador Paper (saldo, tamaño mínimo y precisión del par)
     └─ SQLite: ciclos, decisiones, órdenes, patrimonio y eventos
```

Una vez al día, después del cierre de la vela de 00:00 UTC, cada activo:
1. Consulta las velas cerradas de MEXC y valida la fecha y la antigüedad del dato.
2. Calcula los 20 rezagos y obtiene el pronóstico del modelo.
3. Pide al LLM una propuesta en JSON (comprar, mantener o vender) con una justificación breve.
4. Valida la propuesta y aplica los controles de riesgo:
   - límite de exposición;
   - pérdida diaria máxima de 3 %;
   - stop móvil;
   - antigüedad máxima del dato de 26 h.
5. Ejecuta en Paper, guarda todo y muestra el resultado en la interfaz.

Si falla una dependencia (MEXC, Ollama, clave incorrecta, JSON inválido, dato atrasado, etc.), el agente reintenta con espera creciente y se pausa sin operar. Los nueve escenarios de error del protocolo están demostrados en [`agente/evidencia/demostracion_errores.md`](agente/evidencia/demostracion_errores.md).

### Activos

BTC, ETH, SOL, XRP, BNB, ADA, LTC, TRX, DOGE, MX, FIL, BCH, ZEC, NEAR y DOT contra USDT.
- Cada uno tiene su propio modelo, entrenado y validado con sus datos (TR/VA/TE 70/15/15).
- La estrategia de cada uno (C o D) se eligió con el conjunto de validación.
- Los activos extra se eligieron con una regla de volumen fijada antes de entrenar.

---

## Ejecutarlo

Requisitos: Python 3.13, Node.js y [Ollama](https://ollama.com) con el modelo `llama3.2:3b`. Las instrucciones completas están en [`agente/README.md`](agente/README.md).

```bash
# 1. Entorno de Python y claves (una sola vez, desde esta carpeta)
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r agente/backend/requirements.txt
cp agente/.env.example agente/.env      # y escribe dos claves propias (ver el archivo)
ollama pull llama3.2:3b

# 2. Gateway del LLM y backend (dos terminales, en agente/backend)
uvicorn gateway.main:app --host 127.0.0.1 --port 8001
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Interfaz (en agente/frontend)
npm install && npm run dev               # http://127.0.0.1:5173

# Pruebas y registros
cd agente/backend && python -m pytest    # 97 pruebas automatizadas
python agente/exportar_registros.py      # exporta las bases a CSV y calcula las métricas del informe
```

---

## Estructura del repositorio

| Carpeta o archivo | Contenido |
|---|---|
| [`INFORME.md`](INFORME.md) · [`INFORME.pdf`](INFORME.pdf) | Informe del proyecto final (bloques 14–16 del protocolo) |
| [`agente/`](agente/) | El agente: `backend/` (FastAPI + gateway de Ollama + pruebas), `frontend/` (React + TypeScript), `config/` (configuración de riesgo, LLM y activos), [`README.md`](agente/README.md) y [`CHANGELOG.md`](agente/CHANGELOG.md) (versiones v1.0 a v1.9) |
| [`agente/registros/`](agente/registros/) | Registros del agente en CSV (ciclos, decisiones, órdenes, patrimonio y eventos) y métricas calculadas |
| [`agente/evidencia/`](agente/evidencia/) | Verificación de los modelos en la computadora local, replay histórico de BTC y demostración de los nueve errores |
| [`notebooks/`](notebooks/) | Notebooks de Colab: avances de la práctica (`practica/`) y entrenamiento de los activos extra |
| [`modelos/`](modelos/) | Modelos y escaladores de la práctica (BTC); el agente usa los de `modelos/cap11/` |
| [`activos_extra/`](activos_extra/), [`activos_extra_lote2/`](activos_extra_lote2/), [`activos_extra_lote3/`](activos_extra_lote3/) | Modelos, escaladores, resultados y figuras de los 14 activos extra |
| [`datos/`](datos/), [`resultados/`](resultados/), [`figuras/`](figuras/), [`evidencia_t4/`](evidencia_t4/), [`bitacora/`](bitacora/) | Datos de MEXC, resultados, figuras, evidencia del entrenamiento en GPU T4 y bitácora de la práctica |
| [`Informe/`](Informe/) | Informe final de la práctica y anexos |

---

## Práctica: modelo de pronóstico de BTC/USDT

- **Datos:** velas diarias de BTC/USDT de MEXC, de septiembre de 2018 a noviembre de 2026.
- **División:** entrenamiento (TR), validación (VA) y prueba (TE), en orden cronológico.
- **Modelo final:** ensamble de 3 LSTM (semillas 42, 123 y 2024) con 20 rezagos del rendimiento diario.
- **Estrategia D:** compra si el pronóstico supera δ = 0.0866 % y el cierre está por encima de la SMA20.
- **Congelado antes del TE:** la configuración se fijó con VA y se guardó con su SHA-256 en [`resultados/configuracion_final_congelada.json`](resultados/configuracion_final_congelada.json). El TE se usó una sola vez: −3.25 % frente a −31.57 % de comprar y mantener.

El agente reutiliza ese modelo sin reentrenarlo y comprueba con [`agente/verificar_modelo.py`](agente/verificar_modelo.py) que en esta computadora da las mismas predicciones que en Colab.

---

## Seguridad

- Las claves viven solo en `agente/.env`, que no se sube al repositorio. Se entrega [`agente/.env.example`](agente/.env.example) sin valores.
- La interfaz no guarda claves en el código ni en variables `VITE`.
- Iniciar, detener y cambiar la configuración requieren la clave del backend.
- El LLM no recibe claves, no puede cambiar la configuración y sus acciones no válidas se rechazan.
- No hay ninguna ruta que envíe órdenes reales a MEXC, y no se usa una clave de trading.
