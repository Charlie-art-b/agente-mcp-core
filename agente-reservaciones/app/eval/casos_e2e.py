"""
Dataset de evaluación end-to-end
================================
Cada caso es una CONVERSACIÓN completa (una lista de turnos del usuario) y
lo que se espera al final:

  - `marcadores`: fragmentos que deben aparecer en la respuesta final del
    agente (comparación insensible a mayúsculas y a saltos de línea).
  - `efecto_db`: el cambio que debería haber quedado en la base, o None si
    la conversación no modifica nada. Se verifica consultando Postgres —
    así medimos que la acción REALMENTE pasó, no solo que el agente dijo
    que pasó.

A diferencia de las otras evaluaciones, esta ejecuta las tools de verdad
(crea reservas y tickets reales), así que el harness resetea y siembra la
base antes de correr.

El teléfono 6000-0009 se usa como cliente de prueba en los casos que
tocan la base, para poder verificarlos después.
"""

TELEFONO_PRUEBA = "6000-0009"

CASOS = [
    {
        "nombre": "Consulta de conocimiento (RAG)",
        "turnos": ["¿Cuál es la política de cancelación?"],
        "marcadores": ["24 horas"],
        "efecto_db": None,
    },
    {
        "nombre": "Consulta de disponibilidad",
        "turnos": ["¿Tenés campo mañana para un corte?"],
        "marcadores": ["09:00"],
        "efecto_db": None,
    },
    {
        "nombre": "Reserva completa (multi-turno)",
        "turnos": [
            "¿Tenés campo mañana para un corte?",
            f"Agendame a las 9. Soy Eval E2E, teléfono {TELEFONO_PRUEBA}",
        ],
        "marcadores": [],  # la confirmación varía en redacción; se verifica por DB
        "efecto_db": {"tipo": "reservacion", "telefono": TELEFONO_PRUEBA},
    },
    {
        "nombre": "Escalar un reclamo",
        "turnos": [
            "Me cobraron de más el mes pasado y quiero un reintegro. "
            f"Soy Eval E2E, teléfono {TELEFONO_PRUEBA}",
        ],
        "marcadores": [],
        "efecto_db": {"tipo": "ticket", "telefono": TELEFONO_PRUEBA},
    },
]
