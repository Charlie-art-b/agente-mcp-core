"""
Dataset de evaluación de selección de tools
============================================
Cada caso es un mensaje de usuario y la tool que el agente DEBERÍA elegir
(o None si debería responder directo, sin usar ninguna tool).

Categorías:
  - "conocimiento"   → buscar_conocimiento (preguntas sobre el negocio)
  - "disponibilidad" → consultar_disponibilidad (¿hay campo?)
  - "escalar"        → escalar_caso (reclamos, hablar con humano)
  - "ninguna"        → None (saludos, agradecimientos: responder sin tool)

Por qué no hay casos de crear_reservacion:
  Reservar es multi-turno por regla de negocio (primero hay que consultar
  disponibilidad para tener el horario_id). En un solo turno, ante "quiero
  reservar", lo correcto es que el modelo elija consultar_disponibilidad.
  La selección de crear_reservacion se mide en la evaluación end-to-end.

Los casos "ninguna" son tan importantes como el resto: miden que el agente
NO dispare tools de más ante un simple "hola" o "gracias".
"""

CASOS = [
    # --- Preguntas sobre el negocio → buscar_conocimiento ---
    {
        "mensaje": "¿Cuál es la política de cancelación?",
        "tool_esperada": "buscar_conocimiento",
        "categoria": "conocimiento",
    },
    {
        "mensaje": "¿Aceptan tarjeta de crédito?",
        "tool_esperada": "buscar_conocimiento",
        "categoria": "conocimiento",
    },
    {
        "mensaje": "¿A qué hora abren los sábados?",
        "tool_esperada": "buscar_conocimiento",
        "categoria": "conocimiento",
    },
    {
        "mensaje": "¿Dónde están ubicados?",
        "tool_esperada": "buscar_conocimiento",
        "categoria": "conocimiento",
    },
    # --- Consultas de disponibilidad → consultar_disponibilidad ---
    {
        "mensaje": "¿Tenés campo mañana para un corte?",
        "tool_esperada": "consultar_disponibilidad",
        "categoria": "disponibilidad",
    },
    {
        "mensaje": "¿Hay lugar el viernes por la tarde?",
        "tool_esperada": "consultar_disponibilidad",
        "categoria": "disponibilidad",
    },
    {
        "mensaje": "Quiero ver los horarios libres para manicure el 2 de agosto",
        "tool_esperada": "consultar_disponibilidad",
        "categoria": "disponibilidad",
    },
    # --- Reclamos / hablar con humano → escalar_caso ---
    #
    # Estos casos incluyen el nombre y el teléfono a propósito: escalar_caso
    # requiere el nombre del cliente para registrar el caso (un ticket tiene
    # que saber a quién contactar). Sin ese dato, el modelo NO PUEDE llamar
    # la tool en un solo turno — pediría los datos primero. Con los datos,
    # medimos lo que queremos: el ruteo (¿elige escalar_caso cuando puede?),
    # igual que en la evaluación end-to-end.
    {
        "mensaje": "Quiero hablar con una persona del equipo. Soy Ana Solís, mi teléfono es 8888-4001",
        "tool_esperada": "escalar_caso",
        "categoria": "escalar",
    },
    {
        "mensaje": "Me cobraron de más el mes pasado y quiero un reintegro. Soy Marco Díaz, teléfono 8888-4002",
        "tool_esperada": "escalar_caso",
        "categoria": "escalar",
    },
    {
        "mensaje": "Tengo una queja sobre la atención que recibí ayer. Soy Carla Vega, 8888-4003",
        "tool_esperada": "escalar_caso",
        "categoria": "escalar",
    },
    # --- Sin tool → responder directo ---
    {
        "mensaje": "Hola, buenas tardes",
        "tool_esperada": None,
        "categoria": "ninguna",
    },
    {
        "mensaje": "Muchas gracias, muy amable",
        "tool_esperada": None,
        "categoria": "ninguna",
    },
    {
        "mensaje": "¿Me podés ayudar con algo?",
        "tool_esperada": None,
        "categoria": "ninguna",
    },
]
