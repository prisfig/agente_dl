# Deep Learning para Finanzas — práctica y agente de IA financiero

Repositorio del curso DL para Finanzas: la práctica (capítulos 7–11: datos de MEXC, modelos, señales y evaluación) y el proyecto final, un agente de IA que opera en modo Paper con 15 pares de MEXC.

| Qué | Dónde |
|---|---|
| **Informe del agente** (proyecto final) | [`INFORME.md`](INFORME.md) · [`INFORME.pdf`](INFORME.pdf) |
| Agente: backend FastAPI, gateway de Ollama, interfaz React + TypeScript, configuración y pruebas | [`agente/`](agente/) — instalación y ejecución en [`agente/README.md`](agente/README.md) |
| Registros del agente exportados a CSV (ciclos, decisiones, órdenes, patrimonio, eventos y métricas) | [`agente/registros/`](agente/registros/) |
| Evidencia: verificación de modelos, replay y demostración de los nueve errores | [`agente/evidencia/`](agente/evidencia/) |
| Historial de versiones del agente (v1.0–v1.9) | [`agente/CHANGELOG.md`](agente/CHANGELOG.md) |
| Notebooks de Colab (práctica y activos extra) | [`notebooks/`](notebooks/) |
| Modelos y escaladores versionados | [`modelos/`](modelos/), [`activos_extra/`](activos_extra/), [`activos_extra_lote2/`](activos_extra_lote2/), [`activos_extra_lote3/`](activos_extra_lote3/) |
| Datos, resultados, figuras y evidencia de la práctica | [`datos/`](datos/), [`resultados/`](resultados/), [`figuras/`](figuras/), [`evidencia_t4/`](evidencia_t4/), [`Informe/`](Informe/) |

Las claves no están en el repositorio: se crean en `agente/.env` a partir de [`agente/.env.example`](agente/.env.example). El agente no envía órdenes reales a MEXC; solo lee datos públicos.
