"""
Tests del harness de evaluación de selección de tools
=====================================================
Prueban el cálculo de métricas con un seleccionador falso (un dict
mensaje -> tools), sin llamar a Gemini ni gastar cuota. Lo que se valida
es la lógica del harness: cuándo un caso cuenta como acierto y cómo se
agregan las métricas.
"""

from app.eval.evaluar_tools import evaluar_seleccion


def seleccionador_falso(respuestas):
    """Devuelve una función mensaje -> tools, según un dict fijo."""
    return lambda mensaje: respuestas.get(mensaje, [])


def test_acierto_cuando_elige_la_tool_esperada():
    casos = [
        {"mensaje": "m", "tool_esperada": "buscar_conocimiento", "categoria": "conocimiento"}
    ]
    sel = seleccionador_falso({"m": ["buscar_conocimiento"]})

    m = evaluar_seleccion(sel, casos)

    assert m["accuracy"] == 1.0
    assert m["detalle"][0]["acierto"] is True


def test_fallo_cuando_elige_la_tool_equivocada():
    casos = [
        {"mensaje": "m", "tool_esperada": "consultar_disponibilidad", "categoria": "disponibilidad"}
    ]
    sel = seleccionador_falso({"m": ["escalar_caso"]})

    m = evaluar_seleccion(sel, casos)

    assert m["accuracy"] == 0.0
    assert m["detalle"][0]["seleccionadas"] == ["escalar_caso"]


def test_ninguna_tool_acierta_solo_si_no_pide_ninguna():
    casos = [{"mensaje": "hola", "tool_esperada": None, "categoria": "ninguna"}]

    # No pidió ninguna → acierto
    assert evaluar_seleccion(seleccionador_falso({"hola": []}), casos)["accuracy"] == 1.0
    # Pidió una tool cuando no debía → fallo (sobre-disparo)
    assert evaluar_seleccion(
        seleccionador_falso({"hola": ["buscar_conocimiento"]}), casos
    )["accuracy"] == 0.0


def test_acierta_aunque_pida_la_correcta_entre_varias():
    """Si el modelo pide varias tools y la correcta está, cuenta como acierto."""
    casos = [
        {"mensaje": "m", "tool_esperada": "consultar_disponibilidad", "categoria": "disponibilidad"}
    ]
    sel = seleccionador_falso({"m": ["consultar_disponibilidad", "buscar_conocimiento"]})

    assert evaluar_seleccion(sel, casos)["accuracy"] == 1.0


def test_accuracy_por_categoria():
    casos = [
        {"mensaje": "a", "tool_esperada": "buscar_conocimiento", "categoria": "conocimiento"},
        {"mensaje": "b", "tool_esperada": "buscar_conocimiento", "categoria": "conocimiento"},
        {"mensaje": "c", "tool_esperada": "escalar_caso", "categoria": "escalar"},
    ]
    sel = seleccionador_falso(
        {"a": ["buscar_conocimiento"], "b": ["escalar_caso"], "c": ["escalar_caso"]}
    )

    m = evaluar_seleccion(sel, casos)

    assert m["accuracy"] == 2 / 3
    assert m["por_categoria"]["conocimiento"] == {"aciertos": 1, "total": 2}
    assert m["por_categoria"]["escalar"] == {"aciertos": 1, "total": 1}
