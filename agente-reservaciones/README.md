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
| LLM | Gemini API (Google) |
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
   Cliente del agente (Gemini API)
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
GEMINI_API_KEY=          # hace falta desde la Fase 4
GEMINI_MODEL=gemini-3.6-flash
```

La API key de Gemini se saca en <https://aistudio.google.com/apikey> —
no pide tarjeta de crédito y los modelos Flash tienen capa gratuita.

> En la capa gratuita, Google puede usar el contenido enviado para
> mejorar sus modelos. Para desarrollo con datos de ejemplo no importa,
> pero antes de procesar datos de clientes reales hay que pasar a una
> capa donde eso no aplique.

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

## Agente: Fase 4

El agente es el "cerebro" que decide qué tools ejecutar. Conecta Gemini (LLM)
con el servidor MCP (tools) y orquesta todo para responder consultas del usuario.

### Arquitectura del Agente

```
Usuario: "¿Tenés turno para corte mañana?"
                   ↓
         AgenteReservaciones
                   ↓
         [Gemini analiza la consulta]
                   ↓
     Decide: "Necesito consultar_disponibilidad"
                   ↓
         ClienteMCP ejecuta la tool
                   ↓
         [Gemini procesa el resultado]
                   ↓
     Respuesta: "Sí, tengo turnos libres mañana a las..."
```

### Correr el agente

**1. Setup (primera vez)**

```bash
# Clonar el proyecto e instalar dependencias (ya cubierto arriba)
# ...

# Poblar la BD y el vector store
docker compose up -d postgres
python -m app.db.seed
python -m app.rag.ingest

# Obtener API key de Gemini en https://aistudio.google.com/apikey
# Agregarlo a .env:
# GEMINI_API_KEY=tu_clave_aqui
# GEMINI_MODEL=gemini-3.6-flash
```

**2. Modo interactivo (pruebas manuales)**

```bash
python scripts/chat.py
```

> Los scripts de prueba manual (chat interactivo, verificaciones sueltas)
> viven en `scripts/`, no en `tests/`. `tests/` es solo para tests de
> pytest de verdad — un script manual ahí rompe la recolección de pytest.

Esto abre un chat donde puedes hacer preguntas. El agente:
- Analiza la consulta con Gemini
- Decide qué tool ejecutar (o si simplemente responder con conocimiento)
- Ejecuta la tool a través del servidor MCP
- Devuelve una respuesta en lenguaje natural

Ejemplos de consultas:

```
"¿Qué servicios ofrecen?"                    → buscar_conocimiento
"¿Hay disponibilidad para corte mañana?"     → consultar_disponibilidad
"Quiero reservar para mañana a las 14:00"    → consultar_disponibilidad + crear_reservacion
"Necesito cancelar mi cita"                   → escalar_caso (porque no hay tool de cancelación)
```

**3. API HTTP (futuro: client web / WhatsApp)**

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Endpoints:
- `POST /consulta` - Procesar una consulta
  ```json
  {"pregunta": "¿Hay disponibilidad mañana?"}
  ```
- `GET /estado` - Health check
- `POST /reiniciar` - Descarta la conversación actual y arranca una nueva
- Docs interactivos: `http://localhost:8000/docs`

**4. Interfaz web (chat en el navegador)**

Un chat construido con Streamlit que habla con la API HTTP — no importa el
agente directamente. Es deliberado: la interfaz es "un canal más", igual
que lo será WhatsApp, y ambos pegan al mismo endpoint sin tocar la lógica.

Se corre en dos terminales, ambas desde la raíz del proyecto:

```bash
# Terminal 1 — la API con el agente
python -m uvicorn app.main:app --port 8000

# Terminal 2 — la interfaz
streamlit run app/interfaz_web.py
```

Y se abre <http://localhost:8501> en el navegador. La barra lateral muestra
si la API está conectada, trae preguntas de ejemplo, y un botón para
arrancar una conversación nueva.

> Es una demo de un solo usuario: el agente vive como instancia única en
> la API, así que dos pestañas abiertas comparten la misma conversación.

**5. Panel de operación (métricas)**

Un dashboard de Streamlit SEPARADO del chat: es la vista del dueño/equipo
del negocio (interacciones, costo, latencia, uso por tool), no del cliente.
Como el chat, no toca la base directo — consume la API (`GET /metricas`).

```bash
# Con la API ya corriendo (terminal 1 de arriba), en otra terminal:
streamlit run app/dashboard.py --server.port 8502
```

Y se abre <http://localhost:8502>. Las métricas salen de lo que registra la
Fase 6 en `interacciones_log`, así que aparecen a medida que se usa el chat.

### Cómo funciona el agente

1. **Inicialización**: Conecta con Gemini API y lanza el servidor MCP en un subprocess

2. **Análisis de consulta**: Gemini lee la pregunta y el contexto (tools disponibles, fechas, etc.)

3. **Selección de tool**: Gemini decide si necesita ejecutar alguna tool
   - Si no: devuelve una respuesta directa
   - Si sí: genera un comando `[TOOL: nombre] (arg1=valor1, arg2=valor2)`

4. **Ejecución**: El cliente MCP ejecuta la tool a través del servidor (subprocess con stdio)

5. **Post-procesamiento**: Gemini lee el resultado y genera una respuesta natural

6. **Historial**: El agente mantiene el historial de la conversación para dar contexto a Gemini

### Personalización

El prompt del sistema está en `app/agente/agent.py` en la función `_construir_prompt_sistema()`.
Ahí se define:

- Qué tools tiene el agente disponible y cuándo usarlas
- Tono y personalidad del agente
- Reglas de negocio (ej. "nunca inventes un horario_id")
- Formato de respuesta

Edítalo para ajustar el comportamiento a tu caso de uso.

## Estado del proyecto

- [x] Fase 0 — Fundaciones (estructura, Docker, stack definido)
- [x] Fase 1 — Base de conocimiento (RAG): chunking, vector store (Chroma),
      búsqueda semántica, tests end-to-end
- [x] Fase 2 — Datos de negocio (Postgres)
- [x] Fase 3 — Servidor MCP: las 4 tools expuestas vía protocolo, con
      tests de la lógica y de la capa de protocolo (61 en total)
- [x] Fase 4 — Agente (Gemini + MCP), con API HTTP e interfaz web de chat
- [x] Fase 5 — Evaluación: harness con tres métricas (recuperación del RAG,
      selección de tools, y end-to-end con correctitud/latencia/costo).
      Ver `FASE_5_EVALUACION.md` y `app/eval/`.
- [x] Fase 6 — Logging y observabilidad: cada interacción se registra en
      `interacciones_log` (pregunta, tools con input/output, tokens, costo,
      latencia), y un panel de operador aparte (`app/dashboard.py`) muestra
      las métricas agregadas vía el endpoint `GET /metricas`.
- [ ] Fase 7 — Demo y presentación

## Resultados de evaluación

Números medidos con el harness de la Fase 5 (`python -m app.eval.evaluar_*`).
Detalle completo, hallazgos y advertencias en
[`FASE_5_EVALUACION.md`](FASE_5_EVALUACION.md).

### Recuperación del RAG (búsqueda semántica)

Sobre 12 preguntas, la mitad parafraseadas sin palabras en común con la
respuesta (para medir significado, no coincidencia de texto).

| Métrica | Valor |
|---|---|
| recall@1 | 50% |
| recall@3 | 100% |
| MRR | 0.708 |
| Casos difíciles (semánticos) | 6/6 |

### Selección de tools (`gemini-3.6-flash`)

¿El agente elige la tool correcta para cada mensaje?

| Categoría | Acierto |
|---|---|
| Preguntas del negocio (`buscar_conocimiento`) | 4/4 |
| Disponibilidad (`consultar_disponibilidad`) | 3/3 |
| Sin tool (responder directo) | 3/3 |
| Escalar (`escalar_caso`) | 0/3 |
| **Global** | **77% (10/13)** |

### End-to-end (`gemini-3.5-flash`)

Conversaciones completas, verificando en Postgres que la acción realmente
ocurrió (no que el agente diga que sí).

| Métrica | Valor |
|---|---|
| Correctitud | 100% (4/4) |
| Costo por conversación | ~$0.0003 (≈ 3.000 por dólar) |
| Tokens (4 conversaciones) | ~14.400 |

### Hallazgos

- **`escalar_caso` no dispara ante reclamos "pelados"** (0/3), y sigue en 0%
  incluso con el modelo más capaz — o sea, es un tema de prompt, no de
  modelo. En una conversación real con datos de contacto SÍ escala (el
  end-to-end lo confirma). Mejora pendiente: reforzar la descripción de la
  tool y el prompt del sistema.
- **La latencia no se puede medir limpia en la capa gratuita:** los
  reintentos por rate limit (429/503) inflan los tiempos. En condiciones sin
  contención ronda los ~9s por conversación; para números confiables hace
  falta capa paga.
- El costo mostrado es una estimación a partir de los tokens (exactos) y una
  tarifa de referencia; verificá el precio actual en la doc de Gemini.
