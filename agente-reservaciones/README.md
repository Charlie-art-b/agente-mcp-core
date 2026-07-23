# Agente de Reservaciones con MCP + RAG + Evaluación

Un agente de IA que combina **conocimiento** (RAG) con **acción real** (herramientas vía MCP)
sobre el dominio de reservaciones de un negocio pequeño (salón de belleza, restaurante,
consultorio, etc.).

A diferencia de un chatbot de FAQ, este agente no solo responde preguntas: puede consultar
disponibilidad, crear una reservación, o escalar un caso a un humano — y todo queda medido
con métricas reales, no solo "funciona en la demo".

> Este es el "corazón" del proyecto: MCP + RAG + agente + evaluación. La visión completa
> incluye conectarlo a WhatsApp y venderlo como módulo para negocios pequeños en Costa Rica
> y el mundo — esa capa comercial (multi-tenant, WhatsApp, billing) se desarrolla en una fase
> posterior con inversión, y no vive en este repo público.

## Por qué este proyecto

- El estándar que la industria está adoptando para conectar IA con sistemas reales es
  **MCP (Model Context Protocol)** — este proyecto lo usa de forma nativa, no como wrapper.
- La mayoría de proyectos de IA en portafolio son demos sin medición. Este tiene un
  **harness de evaluación real**: dataset de prueba, métricas de recuperación (RAG),
  métricas de selección de herramienta, y métricas end-to-end.
- Cada interacción queda registrada (logging estructurado): qué preguntó el usuario,
  qué tool se ejecutó, cuánto tardó, cuánto costó.

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| LLM | Claude API (Anthropic) |
| Protocolo de tools | MCP (Model Context Protocol), SDK oficial |
| Backend | FastAPI |
| Base de datos | PostgreSQL |
| Vector store (RAG) | ChromaDB |
| Evaluación | Harness propio en Python |
| Contenedores | Docker + docker-compose |
| CI | GitHub Actions |

## Arquitectura

```
Usuario (web hoy / WhatsApp mañana)
        │
   Cliente del agente (Claude API)
        │
   Servidor MCP  ──►  buscar_conocimiento   (RAG sobre Chroma)
        │        ──►  consultar_disponibilidad (Postgres)
        │        ──►  crear_reservacion        (Postgres)
        │        ──►  escalar_caso             (marca ticket)
        │
   Logging / Evaluación  ──►  cada llamada queda registrada y medida
```

## Estructura del repo

```
app/
├── mcp_server/   # Servidor MCP y definición de tools expuestas
├── tools/        # Implementación de cada acción de negocio
├── rag/          # Pipeline de chunking, embeddings, búsqueda semántica
├── eval/         # Harness de evaluación (dataset + métricas)
├── logging/      # Registro estructurado de interacciones
└── db/           # Modelos y schema de Postgres
data/
├── documents/    # Base de conocimiento (FAQs, políticas)
└── seed/         # Datos de ejemplo para desarrollo
tests/            # Tests automatizados (corren en CI)
```

## Cómo correr el proyecto

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

docker compose up -d postgres  # levanta PostgreSQL 16
python -m app.db.seed          # datos de ejemplo
python -m app.rag.ingest       # ingesta la base de conocimiento

pytest -v                      # 61 tests
```

Creá un `.env` en la raíz del proyecto con al menos esto:

```
DATABASE_URL=postgresql://agente:agente_dev_password@localhost:5432/agente_reservaciones
ANTHROPIC_API_KEY=       # hace falta desde la Fase 4
CLAUDE_MODEL=claude-haiku-4-5
```

> El host es `localhost` porque el compose publica el puerto 5432 del
> contenedor en tu máquina. Si algún día corrés el código *dentro* de
> Docker, ahí el host es `postgres` (el nombre del servicio) — pero eso
> lo define el `environment:` del compose, no hace falta tocar el `.env`.

**En Windows**, ChromaDB y onnxruntime necesitan el *Visual C++
Redistributable*. Sin él, la ingesta falla con un `ImportError` de DLL
que no dice cuál falta realmente:

```powershell
winget install --id Microsoft.VCRedist.2015+.x64 -e
```

## Servidor MCP

Expone las 4 tools del negocio por Model Context Protocol, para que
cualquier cliente compatible (Claude Desktop, Claude Code, un cliente
propio con el SDK) las descubra y ejecute:

| Tool | Qué hace | Fuente |
|---|---|---|
| `buscar_conocimiento` | Responde preguntas de información | RAG / Chroma |
| `consultar_disponibilidad` | Horarios libres en una fecha | Postgres |
| `crear_reservacion` | Agenda un horario | Postgres |
| `escalar_caso` | Abre un ticket para un humano | Postgres |

```bash
python app/mcp_server/server.py     # transporte stdio
```

El servidor se puede lanzar desde cualquier directorio: resuelve sus
rutas a partir de la ubicación del paquete, no del directorio actual
(ver `app/rutas.py`).

Para registrarlo en un cliente MCP, ver `.mcp.json` en la raíz del repo.
Ese archivo apunta al intérprete del venv, así que en Linux o macOS hay
que cambiar `.venv/Scripts/python.exe` por `.venv/bin/python`.

## RAG: probarlo ya mismo (sin Docker, sin Postgres)

El RAG es independiente del resto, así que se puede correr y probar solo:

```bash
pip install -r requirements.txt

# Ingesta los documentos de data/documents/ al vector store local
python -m app.rag.ingest

# Corre los tests (chunking + guardar + buscar, todo probado)
pytest tests/test_rag.py -v
```

La primera vez que corras la ingesta, Chroma va a descargar un modelo de
embeddings liviano (~90 MB, se cachea localmente, no se vuelve a
descargar). Necesitás conexión a internet normal para ese único paso.

Los documentos de conocimiento van en `data/documents/` como `.md` o
`.txt`. El archivo `ejemplo_prueba.md` es solo contenido de prueba —
reemplazalo por tu propia base de conocimiento cuando quieras.

## Estado del proyecto

- [x] Fase 0 — Fundaciones (estructura, Docker, stack definido)
- [x] Fase 1 — Base de conocimiento (RAG): chunking, vector store (Chroma),
      búsqueda semántica, tests end-to-end
- [x] Fase 2 — Datos de negocio (Postgres)
- [x] Fase 3 — Servidor MCP: las 4 tools expuestas vía protocolo, con
      tests de la lógica y de la capa de protocolo (61 en total)
- [ ] Fase 4 — Agente
- [ ] Fase 5 — Evaluación
- [ ] Fase 6 — Logging y observabilidad
- [ ] Fase 7 — Demo y presentación

## Resultados de evaluación

_Se completa en la Fase 5, con números reales de precisión, costo y latencia._
