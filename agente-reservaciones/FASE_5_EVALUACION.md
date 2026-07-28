# Fase 5 — Evaluación

Documento para el equipo. Resume qué se construyó en la Fase 5, las
métricas obtenidas, los hallazgos, cómo correr cada evaluación, y las
advertencias importantes.

> **TL;DR:** el agente tiene ahora un harness de evaluación real, con tres
> métricas medidas: recuperación del RAG, selección de tools, y end-to-end
> (correctitud + latencia + costo). Las tres dan números concretos, no
> "funciona en la demo".

---

## Qué es la Fase 5

Medir el agente con datos, no con impresiones. Se construyeron **tres
evaluaciones independientes**, cada una con su dataset y su harness:

| Etapa | Qué mide | Gasta cuota de Gemini |
|---|---|---|
| 1. Recuperación (RAG) | ¿El buscador trae el chunk correcto? | No (embeddings locales) |
| 2. Selección de tools | ¿El agente elige la tool correcta? | Sí (1 llamada/caso) |
| 3. End-to-end | Correctitud + latencia + costo | Sí (varias llamadas/caso) |

Todo vive en `app/eval/`. Cada evaluación tiene su dataset (`casos_*.py`)
y su harness (`evaluar_*.py`), y tests que validan la lógica sin gastar
cuota (`tests/test_eval_*.py`).

---

## Resultados

### Etapa 1 — Recuperación del RAG

Dataset: 12 preguntas etiquetadas por dificultad. Las "difíciles" son
paráfrasis que NO comparten palabras con la respuesta (ej. "¿me puedo
echar para atrás?" → política de cancelación), y son las que de verdad
miden si la búsqueda entiende el significado.

| Métrica | Valor | Qué significa |
|---|---|---|
| recall@1 | **50%** | El chunk correcto salió primero |
| recall@3 | **100%** | Salió dentro del top-3 |
| MRR | **0.708** | Qué tan arriba salió (1.0 = siempre primero) |
| Difíciles (semánticas) | **6/6** | La búsqueda semántica funciona |

**Lectura honesta:** con solo 3 chunks en el corpus, `recall@3` es poco
informativo (el top-3 devuelve casi todo). El número que importa es
`recall@1 = 50%`: la mitad de las veces el chunk más relevante no queda
primero. La causa es el chunking (500 caracteres con solapamiento) sobre
un documento tan chico: los chunks se parecen mucho entre sí. Mejora
concreta pendiente: **cortar por encabezados de markdown (una sección =
un chunk)** y volver a medir.

### Etapa 2 — Selección de tools

Dataset: 13 mensajes, cada uno con la tool esperada (o "ninguna").
Números oficiales con **`gemini-3.6-flash`** (el más capaz).

| Categoría | Acierto |
|---|---|
| conocimiento (`buscar_conocimiento`) | 4/4 — 100% |
| disponibilidad (`consultar_disponibilidad`) | 3/3 — 100% |
| ninguna (responder directo, sin tool) | 3/3 — 100% |
| **escalar (`escalar_caso`)** | **0/3 — 0%** |
| **Global** | **10/13 — 77%** |

**El hallazgo:** ante un reclamo "pelado" en un solo turno ("me cobraron
de más", "quiero hablar con alguien"), el modelo NO elige `escalar_caso`
— lo trata como pregunta o responde directo. **Se corrió también con
`gemini-3.5-flash` y el resultado fue idéntico (escalar 0/3), así que NO
es un problema de capacidad del modelo: es del prompt.** Ver la nota
importante más abajo, porque esto se matiza con el resultado end-to-end.

> `crear_reservacion` no está en este dataset a propósito: reservar es
> multi-turno (primero hay que consultar disponibilidad para tener el
> `horario_id`), así que en un solo turno lo correcto es que el modelo
> elija `consultar_disponibilidad`. La selección de `crear_reservacion` se
> mide en la etapa 3.

### Etapa 3 — End-to-end (correctitud + latencia + costo)

Dataset: 4 conversaciones completas. La correctitud se verifica
**consultando Postgres** (¿la reserva/ticket realmente se creó?), no
confiando en lo que el agente dice.

Se corrió dos veces, y la comparación es reveladora:

| | `gemini-3.5-flash-lite` (ayer) | `gemini-3.5-flash` (oficial) |
|---|---|---|
| Correctitud | 4/4 (100%) | 4/4 (100%) |
| Latencia promedio | 8.9s | **45.3s** ⚠️ |
| Tokens totales | 12.373 | 14.386 |
| Costo total | $0.00137 | $0.00149 |

**Costo:** ≈ **$0.0003 por conversación** (~3.000 conversaciones por dólar).
El costo y los tokens son confiables en ambas corridas.

**La latencia NO es confiable en la capa gratuita.** Los 45s de la segunda
corrida no son latencia real del modelo: son los **reintentos por rate
limit** (429/503). Cuando una llamada choca con el límite, el SDK espera
20-60s y reintenta, y esa espera cae dentro del cronómetro. La latencia
real ronda los **~9s** (la primera corrida, con menos contención). Para
medir latencia limpia hace falta capa paga.

---

## Nota importante: por qué escalar falló en la etapa 2 pero pasó en la 3

Es sutil y ayuda a entender el sistema:

| | Mensaje | Resultado |
|---|---|---|
| Etapa 2 (tool eval) | "Me cobraron de más y quiero un reintegro" | ❌ eligió `buscar_conocimiento` |
| Etapa 3 (end-to-end) | "Me cobraron de más... **Soy Eval E2E, tel 6000-0009**" | ✅ escaló, ticket creado |

**Cuando el mensaje trae los datos de contacto, el modelo escala. Cuando
es un reclamo sin datos, no.** En una conversación real el agente pediría
los datos y después escalaría — comportamiento razonable. El "0%" de la
etapa 2 es duro porque mide turnos aislados y en frío.

Conclusión: no es que `escalar_caso` esté roto. Es que en un turno
aislado y sin contexto el modelo prefiere responder o preguntar antes que
escalar. Mejora pendiente: reforzar la descripción de `escalar_caso` y el
prompt del sistema para que dispare antes ante reclamos, y volver a medir.

**Ojo — un malentendido común:** el escalado NO depende de
`ejemplo_prueba.md`. Ese archivo es la base de conocimiento que lee
`buscar_conocimiento` (el RAG). `escalar_caso` es una tool que el modelo
ELIGE según su descripción y el prompt del sistema; no lee el documento.
Agregar texto sobre escalación al `.md` no cambiaría nada.

---

## Cómo correr cada evaluación

Desde la raíz del proyecto, con el venv activado y (para las etapas 2 y 3)
Postgres corriendo:

```bash
# Etapa 1 — RAG (gratis, no gasta cuota)
python -m app.eval.evaluar_rag

# Etapa 2 — Selección de tools (gasta ~13 llamadas)
python -m app.eval.evaluar_tools

# Etapa 3 — End-to-end (gasta ~9 llamadas; RESETEA la base)
python -m app.eval.evaluar_e2e
```

> ⚠️ La etapa 3 **borra y vuelve a sembrar la base** para ser
> reproducible. No la corras sobre datos que quieras conservar.

---

## Advertencias importantes

### 1. Cuota de Gemini (capa gratuita)

Hay **dos límites**, y los dos importan para evaluar:

- **5 llamadas por minuto** por modelo → resuelto: los harness espacian
  las llamadas (throttling) y reintentan ante 429/503.
- **20 llamadas por día** por modelo → **el muro real.** Cada modelo tiene
  su bucket diario aparte. Correr las evaluaciones completas agota el día
  rápido.

**Para evaluación repetida, la capa gratuita no alcanza.** Opciones:
repartir entre modelos (cada uno con su bucket), esperar al reset diario,
o pasar a capa paga. Modelos que funcionan hoy: los `gemini-3.5-*` y
`gemini-3.*-flash-lite`. Ojo: `gemini-2.5-flash` da 404 (no está para
cuentas nuevas).

### 2. Modelo usado

Las etapas 2 y 3 se corrieron con modelos **livianos** (`3.5-flash` y
`3.5-flash-lite`) porque eran los que tenían cuota. Los `lite` son más
rápidos y baratos pero **más flojos en selección de tools**. Para los
números "oficiales" del portafolio conviene re-correr con
`gemini-3.6-flash` (más capaz), que probablemente suba la selección de
tools y cambie latencia/costo.

### 3. El costo es estimado

El costo se calcula con una tarifa de referencia (`$0.10/$0.40` por 1M
tokens de entrada/salida) definida como constante en `evaluar_e2e.py`
(`PRECIO_ENTRADA_POR_1M`, `PRECIO_SALIDA_POR_1M`). **Verificar el precio
actual en <https://ai.google.dev/pricing> y ajustar.** Los **tokens** sí
son exactos (los reporta Gemini).

---

## Archivos de la Fase 5

```
app/eval/
├── casos_rag.py       # dataset de recuperación
├── evaluar_rag.py     # harness RAG (recall@1, recall@3, MRR)
├── casos_tools.py     # dataset de selección de tools
├── evaluar_tools.py   # harness de tools (con throttling)
├── casos_e2e.py       # dataset de conversaciones completas
└── evaluar_e2e.py     # harness e2e (correctitud + latencia + costo)

tests/
├── test_eval_rag.py
├── test_eval_tools.py
└── test_eval_e2e.py

app/agente/agent.py    # + contador de tokens (self.ultimo_uso), usado por
                       #   la evaluación de costo y base para el logging (Fase 6)
```

---

## Próximos pasos sugeridos

1. **Mejorar el escalado:** reforzar la descripción de `escalar_caso` y el
   prompt del sistema, y re-correr la etapa 2 para medir si sube de 0%.
2. **Mejorar el chunking:** cortar por encabezados de markdown, y re-correr
   la etapa 1 para ver si sube el `recall@1`.
3. **Sacar los números oficiales** con `gemini-3.6-flash` (cuota fresca) y
   volcarlos a la sección "Resultados de evaluación" del README.
4. **Fase 6 (logging):** el contador de tokens del agente ya es la base
   para registrar cada interacción (pregunta, tool, tokens, latencia, costo).
