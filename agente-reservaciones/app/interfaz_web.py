"""
Interfaz web del agente (Streamlit)
====================================
Un chat en el navegador para conversar con el agente de reservaciones.

Diseño: esta interfaz NO importa el agente ni toca la base de datos. Habla
únicamente con la API HTTP (app/main.py) vía httpx — igual que lo haría
cualquier otro canal (WhatsApp, otra web). Si mañana el agente cambia por
dentro (otro modelo, function calling nativo, lo que sea), esta interfaz
no se entera: el contrato es "mando una pregunta, recibo un texto".

Cómo correr (dos terminales, desde la raíz del proyecto):

    # Terminal 1 — la API con el agente
    python -m uvicorn app.main:app --port 8000

    # Terminal 2 — esta interfaz
    streamlit run app/interfaz_web.py

Y abrir http://localhost:8501 en el navegador.

Nota: es una demo de UN usuario. El agente vive como instancia única en la
API, así que dos pestañas abiertas comparten la misma conversación.
"""

import os

import httpx
import streamlit as st


API_URL = os.environ.get("AGENTE_API_URL", "http://localhost:8000")

COLOR_TEXTO = "#E9E4DB"
COLOR_TENUE = "#8A8175"
COLOR_BORDE = "#2A2521"
COLOR_ACENTO = "#C2A878"

SALUDO_INICIAL = (
    "Hola, soy el asistente de reservaciones.\n\n"
    "Puedo contarte sobre el negocio, consultar horarios disponibles, "
    "agendarte una cita o pasar tu caso a una persona del equipo. "
    "¿En qué te ayudo?"
)

PREGUNTAS_EJEMPLO = [
    "¿Cuál es la política de cancelación?",
    "¿Tenés campo mañana para un corte?",
    "Quiero hablar con una persona",
]

ETIQUETAS = {"assistant": "Agente", "user": "Vos"}


# --- Comunicación con la API ---


def api_disponible() -> tuple[bool, str]:
    """Devuelve (True, "") si la API responde, o (False, detalle) si no."""
    try:
        r = httpx.get(f"{API_URL}/estado", timeout=5.0)
        r.raise_for_status()
        return True, ""
    except httpx.HTTPStatusError as e:
        try:
            detalle = e.response.json().get("detail", "")
        except Exception:
            detalle = e.response.text[:200]
        return False, detalle
    except httpx.HTTPError:
        return False, ""


def preguntar_al_agente(pregunta: str) -> str:
    """
    Manda la pregunta a la API y devuelve la respuesta del agente.

    El timeout es generoso: un turno puede incluir levantar el servidor MCP
    (con la carga del modelo de embeddings la primera vez) más dos llamadas
    a Gemini.
    """
    r = httpx.post(
        f"{API_URL}/consulta",
        json={"pregunta": pregunta},
        timeout=httpx.Timeout(180.0, connect=5.0),
    )
    r.raise_for_status()
    return r.json()["respuesta"]


def reiniciar_conversacion() -> None:
    """Descarta la conversación en la API y limpia el chat local."""
    try:
        httpx.post(f"{API_URL}/reiniciar", timeout=10.0)
    except httpx.HTTPError:
        # Si la API no está, igual limpiamos el chat local: al volver a
        # estar disponible, la primera consulta crea un agente fresco.
        pass
    st.session_state.mensajes = [{"rol": "assistant", "texto": SALUDO_INICIAL}]


# --- Piezas de presentación ---


def etiqueta(texto: str, margen: str = "0 0 6px 0") -> str:
    """Rótulo chico en mayúsculas espaciadas, estilo editorial."""
    return (
        f'<div style="font-size:10px; letter-spacing:.24em; '
        f"text-transform:uppercase; color:{COLOR_TENUE}; "
        f'margin:{margen};">{texto}</div>'
    )


def render_mensaje(rol: str, texto: str) -> None:
    """Una burbuja del chat, con su rótulo de quién habla."""
    with st.chat_message(rol):
        st.markdown(etiqueta(ETIQUETAS[rol]), unsafe_allow_html=True)
        st.markdown(texto)


# --- Página ---

st.set_page_config(
    page_title="Agente de Reservaciones",
    layout="centered",
)

# Retoques sobre el tema de .streamlit/config.toml. CSS deliberadamente
# corto; si algún selector interno de Streamlit cambia de nombre en una
# versión futura, lo peor que pasa es que vuelva el aspecto por defecto.
st.markdown(
    f"""
    <style>
        /* Burbujas del chat como tarjetas sobrias */
        [data-testid="stChatMessage"] {{
            background: #1A1714;
            border: 1px solid {COLOR_BORDE};
            border-radius: 4px;
            padding: 18px 20px;
            margin-bottom: 10px;
        }}

        /* Sin avatares: el rótulo dentro de la burbuja dice quién habla */
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="chatAvatarIcon-user"],
        [data-testid="chatAvatarIcon-assistant"] {{
            display: none;
        }}

        /* Botones: contorno fino, acento al pasar el mouse */
        .stButton button {{
            background: transparent;
            border: 1px solid {COLOR_BORDE};
            border-radius: 4px;
            color: #D8D2C7;
            font-size: 13px;
        }}
        .stButton button:hover {{
            border-color: {COLOR_ACENTO};
            color: {COLOR_TEXTO};
        }}

        header[data-testid="stHeader"] {{ background: transparent; }}
        footer {{ visibility: hidden; }}
    </style>
    """,
    unsafe_allow_html=True,
)

if "mensajes" not in st.session_state:
    # El saludo es local (no gasta una llamada a Gemini).
    st.session_state.mensajes = [{"rol": "assistant", "texto": SALUDO_INICIAL}]


# --- Barra lateral ---

with st.sidebar:
    st.markdown(
        f'<div style="font-family:Georgia, \'Times New Roman\', serif; '
        f'font-size:22px; color:{COLOR_TEXTO};">Reservaciones</div>'
        + etiqueta("Demo del agente · Fase 4", margen="4px 0 0 0"),
        unsafe_allow_html=True,
    )

    st.divider()

    conectada, detalle_error = api_disponible()
    if conectada:
        st.markdown(
            f'<div style="font-size:13px;"><span style="color:#9DB88F;">&#9679;</span>'
            f'&nbsp; <span style="color:#CFC8BC;">API conectada</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:13px;"><span style="color:#B4726A;">&#9679;</span>'
            f'&nbsp; <span style="color:#CFC8BC;">API no disponible</span></div>',
            unsafe_allow_html=True,
        )
        st.caption("Levantala desde la raíz del proyecto:")
        st.code("python -m uvicorn app.main:app --port 8000", language="powershell")
        if detalle_error:
            st.caption(f"Detalle: {detalle_error}")

    st.divider()

    st.markdown(etiqueta("Probá preguntarle", margen="0 0 10px 0"), unsafe_allow_html=True)
    for ejemplo in PREGUNTAS_EJEMPLO:
        if st.button(ejemplo, use_container_width=True):
            st.session_state.pendiente = ejemplo
            st.rerun()

    st.divider()

    if st.button("Nueva conversación", use_container_width=True):
        reiniciar_conversacion()
        st.rerun()

    st.caption("Gemini · MCP · PostgreSQL · Chroma")
    st.caption(
        "Demo de un solo usuario: todas las pestañas comparten la misma conversación."
    )


# --- Encabezado ---

st.markdown(
    f"""
    <div style="text-align:center; padding: 6px 0 2px 0;">
        {etiqueta("Asistente virtual", margen="0 0 8px 0")}
        <div style="font-family:Georgia, 'Times New Roman', serif;
                    font-size:34px; color:{COLOR_TEXTO}; line-height:1.2;">
            Agente de Reservaciones
        </div>
        <div style="font-size:13px; color:{COLOR_TENUE}; margin-top:6px;">
            Disponibilidad &middot; Reservas &middot; Consultas
        </div>
    </div>
    <hr style="border:none; border-top:1px solid {COLOR_BORDE}; margin:18px 0 22px 0;">
    """,
    unsafe_allow_html=True,
)


# --- Chat ---

for mensaje in st.session_state.mensajes:
    render_mensaje(mensaje["rol"], mensaje["texto"])

pregunta = st.chat_input("Escribí tu consulta…")
if not pregunta and "pendiente" in st.session_state:
    # Una pregunta de ejemplo clickeada en la barra lateral.
    pregunta = st.session_state.pop("pendiente")

if pregunta:
    st.session_state.mensajes.append({"rol": "user", "texto": pregunta})
    render_mensaje("user", pregunta)

    with st.chat_message("assistant"):
        st.markdown(etiqueta(ETIQUETAS["assistant"]), unsafe_allow_html=True)
        with st.spinner("Consultando…"):
            try:
                respuesta = preguntar_al_agente(pregunta)
            except httpx.ConnectError:
                respuesta = (
                    "No pude conectar con la API del agente. "
                    "Fijate que esté corriendo (el comando está en la barra lateral) "
                    "y volvé a intentar."
                )
            except httpx.TimeoutException:
                respuesta = (
                    "La consulta tardó demasiado y se canceló. "
                    "Puede ser la primera carga del servidor — probá de nuevo."
                )
            except httpx.HTTPStatusError as e:
                try:
                    detalle = e.response.json().get("detail", e.response.text[:300])
                except Exception:
                    detalle = e.response.text[:300]
                respuesta = f"El agente devolvió un error:\n\n`{detalle}`"
        st.markdown(respuesta)

    st.session_state.mensajes.append({"rol": "assistant", "texto": respuesta})
