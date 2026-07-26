"""
Dataset de evaluación del RAG
=============================
Casos de prueba para medir la recuperación semántica: cada uno es una
pregunta de usuario y un `marcador` — un fragmento de texto que TIENE que
aparecer en el chunk correcto. Si el buscador trae ese chunk en el top-k,
el caso pasa.

Los casos vienen etiquetados por `dificultad`:
  - "facil": la pregunta comparte palabras con el documento (un Ctrl+F
    casi alcanzaría).
  - "dificil": la pregunta está parafraseada y NO comparte palabras clave
    con la respuesta ("¿me puedo echar para atrás?" → cancelación). Estos
    son los que de verdad miden si la búsqueda entiende el *significado*
    y no solo las letras.

Cuando reemplaces el documento de ejemplo por una base de conocimiento
real, actualizá estos casos para que apunten a ese contenido.
"""

CASOS = [
    # --- Horario de atención ---
    {
        "pregunta": "¿A qué hora cierran de lunes a viernes?",
        "marcador": "5:00 p.m.",
        "tema": "horario",
        "dificultad": "facil",
    },
    {
        "pregunta": "¿Atienden los fines de semana?",
        "marcador": "sábados",
        "tema": "horario",
        "dificultad": "dificil",
    },
    {
        "pregunta": "¿Puedo pasar un domingo?",
        "marcador": "domingos",
        "tema": "horario",
        "dificultad": "dificil",
    },
    # --- Política de cancelación ---
    {
        "pregunta": "¿Con cuánta anticipación puedo cancelar sin costo?",
        "marcador": "24 horas",
        "tema": "cancelacion",
        "dificultad": "facil",
    },
    {
        "pregunta": "¿Qué pasa si me arrepiento y no aviso?",
        "marcador": "penalización",
        "tema": "cancelacion",
        "dificultad": "dificil",
    },
    {
        "pregunta": "Quiero echarme para atrás con mi reserva",
        "marcador": "cancelaciones",
        "tema": "cancelacion",
        "dificultad": "dificil",
    },
    # --- Métodos de pago ---
    {
        "pregunta": "¿Aceptan SINPE móvil?",
        "marcador": "SINPE",
        "tema": "pagos",
        "dificultad": "facil",
    },
    {
        "pregunta": "¿Puedo pagar con tarjeta de crédito?",
        "marcador": "tarjeta de crédito",
        "tema": "pagos",
        "dificultad": "facil",
    },
    {
        "pregunta": "¿Reciben cheques?",
        "marcador": "cheques",
        "tema": "pagos",
        "dificultad": "dificil",
    },
    # --- Ubicación ---
    {
        "pregunta": "¿Dónde queda el local?",
        "marcador": "parque central",
        "tema": "ubicacion",
        "dificultad": "facil",
    },
    {
        "pregunta": "¿Tienen dónde estacionar el carro?",
        "marcador": "parqueo",
        "tema": "ubicacion",
        "dificultad": "dificil",
    },
    {
        "pregunta": "¿En qué piso están?",
        "marcador": "segundo piso",
        "tema": "ubicacion",
        "dificultad": "facil",
    },
]
