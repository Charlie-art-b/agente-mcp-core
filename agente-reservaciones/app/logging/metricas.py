"""
Métricas de interacciones
=========================
Agrega la tabla `interacciones_log` (que llena app/logging/registro.py) en
números para el panel de operación: cuántas interacciones hubo, cuánto se
gastó, cuánto tardó en promedio, y qué tools se usaron más.

Función pura sobre la base: recibe una sesión, devuelve un dict. La expone
la API en GET /metricas, y el dashboard (app/dashboard.py) la consume.
"""

from datetime import datetime, timezone

from app.db.models import InteraccionLog


def calcular_metricas(sesion) -> dict:
    """
    Devuelve las métricas agregadas de interacciones_log.

    Returns:
        dict con totales, costo, latencia, uso por tool, y las últimas
        interacciones (para una tabla). Si no hay datos, devuelve ceros.
    """
    # Se ordena por fecha y, como desempate, por id descendente: si dos
    # interacciones caen en el mismo instante, la de id mayor (insertada
    # después) queda primero. Sin el desempate, filas con igual creado_en
    # quedarían en orden indefinido.
    filas = (
        sesion.query(InteraccionLog)
        .order_by(InteraccionLog.creado_en.desc(), InteraccionLog.id.desc())
        .all()
    )
    total = len(filas)

    if total == 0:
        return {
            "total_interacciones": 0,
            "interacciones_hoy": 0,
            "costo_total_usd": 0.0,
            "tokens_total": 0,
            "latencia_promedio_ms": 0,
            "uso_por_tool": {},
            "interacciones_sin_tool": 0,
            "ultimas": [],
        }

    inicio_de_hoy = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    costo_total = 0.0
    tokens_total = 0
    latencia_total = 0
    con_latencia = 0
    interacciones_hoy = 0
    uso_por_tool: dict[str, int] = {}
    sin_tool = 0

    for f in filas:
        costo_total += float(f.costo_usd or 0)
        tokens_total += (f.tokens_input or 0) + (f.tokens_output or 0)

        if f.latencia_ms is not None:
            latencia_total += f.latencia_ms
            con_latencia += 1

        if f.creado_en is not None and _asegurar_utc(f.creado_en) >= inicio_de_hoy:
            interacciones_hoy += 1

        if f.tool_llamada:
            # tool_llamada guarda los nombres separados por coma cuando el
            # turno usó varias tools.
            for nombre in f.tool_llamada.split(","):
                uso_por_tool[nombre] = uso_por_tool.get(nombre, 0) + 1
        else:
            sin_tool += 1

    ultimas = [
        {
            "mensaje_usuario": f.mensaje_usuario,
            "tool_llamada": f.tool_llamada or "(ninguna)",
            "tokens": (f.tokens_input or 0) + (f.tokens_output or 0),
            "latencia_ms": f.latencia_ms or 0,
            "costo_usd": float(f.costo_usd or 0),
        }
        for f in filas[:15]
    ]

    return {
        "total_interacciones": total,
        "interacciones_hoy": interacciones_hoy,
        "costo_total_usd": costo_total,
        "tokens_total": tokens_total,
        "latencia_promedio_ms": round(latencia_total / con_latencia) if con_latencia else 0,
        "uso_por_tool": dict(
            sorted(uso_por_tool.items(), key=lambda kv: kv[1], reverse=True)
        ),
        "interacciones_sin_tool": sin_tool,
        "ultimas": ultimas,
    }


def _asegurar_utc(dt: datetime) -> datetime:
    """
    Postgres puede devolver el timestamp sin tzinfo (naive). Se asume UTC
    (que es como lo guarda el modelo) para poder compararlo con hoy.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
