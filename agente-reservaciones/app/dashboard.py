"""
Panel de operación (Streamlit)
==============================
Dashboard de MÉTRICAS del agente, para el dueño/equipo del negocio. Es una
vista de operador, SEPARADA del chat del cliente (app/interfaz_web.py):
otra app, otro puerto, otra audiencia.

Como el chat, no toca la base directo: consume la API (GET /metricas). Así
la lógica de agregación vive en un solo lugar (app/logging/metricas.py) y
el panel es solo presentación.

Cómo correr (desde la raíz del proyecto, con la API levantada):

    # La API (si no está ya corriendo)
    python -m uvicorn app.main:app --port 8000

    # El panel (en otro puerto que el chat)
    streamlit run app/dashboard.py --server.port 8502

Y abrir http://localhost:8502 en el navegador.
"""

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("AGENTE_API_URL", "http://localhost:8000")

COLOR_TEXTO = "#E9E4DB"
COLOR_TENUE = "#8A8175"
COLOR_BORDE = "#2A2521"
COLOR_ACENTO = "#C2A878"


# --- Datos ---


def obtener_metricas() -> dict | None:
    """Trae las métricas de la API, o None si no responde."""
    try:
        r = httpx.get(f"{API_URL}/metricas", timeout=10.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return None


# --- Presentación ---


def etiqueta(texto: str, margen: str = "0 0 6px 0") -> str:
    return (
        f'<div style="font-size:10px; letter-spacing:.24em; '
        f"text-transform:uppercase; color:{COLOR_TENUE}; "
        f'margin:{margen};">{texto}</div>'
    )


def tile(rotulo: str, valor: str) -> str:
    """Un stat tile: un rótulo chico arriba y el número-titular abajo."""
    return f"""
    <div style="background:#1A1714; border:1px solid {COLOR_BORDE};
                border-radius:4px; padding:16px 18px;">
        {etiqueta(rotulo, margen="0 0 8px 0")}
        <div style="font-family:Georgia,'Times New Roman',serif;
                    font-size:30px; color:{COLOR_TEXTO}; line-height:1;">{valor}</div>
    </div>
    """


st.set_page_config(page_title="Panel de operación", layout="wide")

st.markdown(
    """
    <style>
        header[data-testid="stHeader"] { background: transparent; }
        footer { visibility: hidden; }
        .stButton button {
            background: transparent; border: 1px solid #2A2521;
            border-radius: 4px; color: #D8D2C7; font-size: 13px;
        }
        .stButton button:hover { border-color: #C2A878; color: #E9E4DB; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Encabezado ---

col_titulo, col_boton = st.columns([4, 1])
with col_titulo:
    st.markdown(
        etiqueta("Agente de reservaciones · interno")
        + f'<div style="font-family:Georgia,\'Times New Roman\',serif; '
        f'font-size:30px; color:{COLOR_TEXTO}; line-height:1.2;">Panel de operación</div>',
        unsafe_allow_html=True,
    )
with col_boton:
    st.write("")
    actualizar = st.button("Actualizar", use_container_width=True)

st.markdown(
    f'<hr style="border:none; border-top:1px solid {COLOR_BORDE}; margin:16px 0 20px 0;">',
    unsafe_allow_html=True,
)

metricas = obtener_metricas()

if metricas is None:
    st.markdown(
        f'<div style="font-size:14px;"><span style="color:#B4726A;">&#9679;</span>'
        f'&nbsp; API no disponible</div>',
        unsafe_allow_html=True,
    )
    st.caption("Levantá la API desde la raíz del proyecto:")
    st.code("python -m uvicorn app.main:app --port 8000", language="powershell")
    st.stop()

if metricas["total_interacciones"] == 0:
    st.info(
        "Todavía no hay interacciones registradas. Conversá con el agente en el "
        "chat (app/interfaz_web.py) y las métricas van a aparecer acá."
    )
    st.stop()


# --- KPIs (stat tiles) ---

latencia_s = metricas["latencia_promedio_ms"] / 1000
kpis = [
    ("Interacciones", f"{metricas['total_interacciones']:,}"),
    ("Hoy", f"{metricas['interacciones_hoy']:,}"),
    ("Costo total", f"${metricas['costo_total_usd']:.4f}"),
    ("Latencia prom.", f"{latencia_s:.1f}s"),
]
for col, (rotulo, valor) in zip(st.columns(len(kpis)), kpis):
    col.markdown(tile(rotulo, valor), unsafe_allow_html=True)

st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)


# --- Uso por tool (bar chart de una tinta) ---

col_izq, col_der = st.columns([3, 2])

with col_izq:
    st.markdown(etiqueta("Uso por tool"), unsafe_allow_html=True)
    uso = metricas["uso_por_tool"]
    if uso:
        df = pd.DataFrame({"tool": list(uso.keys()), "usos": list(uso.values())})
        st.bar_chart(
            df, x="tool", y="usos", color=COLOR_ACENTO, horizontal=True, height=260
        )
    else:
        st.caption("Ninguna tool ejecutada todavía.")

with col_der:
    st.markdown(etiqueta("Composición"), unsafe_allow_html=True)
    con_tool = metricas["total_interacciones"] - metricas["interacciones_sin_tool"]
    st.markdown(
        tile("Con tool", f"{con_tool:,}"), unsafe_allow_html=True
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown(
        tile("Sin tool (respuesta directa)", f"{metricas['interacciones_sin_tool']:,}"),
        unsafe_allow_html=True,
    )


# --- Últimas interacciones ---

st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
st.markdown(etiqueta("Últimas interacciones"), unsafe_allow_html=True)

tabla = pd.DataFrame(metricas["ultimas"])
if not tabla.empty:
    tabla = tabla.rename(
        columns={
            "mensaje_usuario": "Mensaje",
            "tool_llamada": "Tool",
            "tokens": "Tokens",
            "latencia_ms": "Latencia (ms)",
            "costo_usd": "Costo (USD)",
        }
    )
    tabla["Costo (USD)"] = tabla["Costo (USD)"].map(lambda c: f"${c:.5f}")
    st.dataframe(tabla, use_container_width=True, hide_index=True)
