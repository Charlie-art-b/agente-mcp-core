"""
Tests del servidor MCP
=======================
Prueban la capa de protocolo, no la lógica de negocio (esa ya se prueba
en test_consultar_disponibilidad.py). Lo que se valida acá es que:

  - las tools quedan registradas y visibles para un cliente MCP,
  - el JSON Schema que FastMCP genera desde los type hints coincide con
    la firma real de la función (si se desincronizan, el modelo manda
    argumentos inválidos y es dificilísimo de depurar),
  - una llamada real a través del protocolo devuelve datos usables.

Se usa el cliente en memoria del SDK, así que no hace falta levantar el
proceso del servidor ni tener Postgres corriendo.
"""

import json
import os
import tempfile
from datetime import date

import pytest

from app.db.models import HorarioDisponible, Servicio
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.mcp_server.server import mcp

from mcp.shared.memory import create_connected_server_and_client_session

FECHA_STR = "2026-08-01"


def cliente_mcp():
    """
    Cliente MCP conectado al servidor real, en memoria.

    Se usa como `async with cliente_mcp() as cliente:` dentro de cada test
    y no como fixture async: al ceder el control desde una fixture, anyio
    termina cerrando el contexto en una tarea distinta a la que lo abrió y
    revienta en el teardown.
    """
    return create_connected_server_and_client_session(mcp._mcp_server)


@pytest.fixture
def base_de_prueba(monkeypatch):
    """
    Apunta la tool a una base SQLite temporal con datos de prueba.

    Se usa un archivo y no `:memory:` porque la tool abre y cierra su
    propia sesión: con SQLite en memoria, cada conexión nueva ve una base
    vacía y se perderían los datos sembrados acá.
    """
    ruta = os.path.join(tempfile.mkdtemp(), "prueba.db")
    engine = crear_engine(f"sqlite:///{ruta}")
    crear_tablas(engine)
    fabrica = crear_fabrica_sesiones(engine)

    s = fabrica()
    corte = Servicio(nombre="Corte de cabello", duracion_minutos=30, precio=8000)
    s.add(corte)
    s.flush()
    s.add(
        HorarioDisponible(
            servicio_id=corte.id,
            fecha=date(2026, 8, 1),
            hora_inicio="09:00",
            hora_fin="09:30",
            disponible=True,
        )
    )
    s.commit()
    s.close()

    # Cada tool llama a obtener_sesion() desde su propio módulo, así que se
    # reemplaza en cada uno y no en app.db.session.
    for modulo in (
        "consultar_disponibilidad",
        "crear_reservacion",
        "cancelar_reservacion",
        "escalar_caso",
    ):
        monkeypatch.setattr(f"app.tools.{modulo}.obtener_sesion", lambda: fabrica())

    return ruta


# --- Registro y descubrimiento de tools ---


@pytest.mark.asyncio
async def test_el_servidor_expone_las_tools_esperadas():
    async with cliente_mcp() as cliente:
        resultado = await cliente.list_tools()

    nombres = {t.name for t in resultado.tools}
    assert nombres == {
        "buscar_conocimiento",
        "consultar_disponibilidad",
        "crear_reservacion",
        "cancelar_reservacion",
        "escalar_caso",
    }


@pytest.mark.asyncio
async def test_crear_reservacion_declara_bien_lo_obligatorio_y_lo_opcional():
    """El teléfono y el email son opcionales; el horario y el nombre no."""
    async with cliente_mcp() as cliente:
        resultado = await cliente.list_tools()

    tool = next(t for t in resultado.tools if t.name == "crear_reservacion")

    assert set(tool.inputSchema["required"]) == {"horario_id", "nombre_cliente"}
    assert tool.inputSchema["properties"]["horario_id"]["type"] == "integer"


@pytest.mark.asyncio
async def test_cada_tool_tiene_descripcion_tomada_del_docstring():
    """La descripción es lo que el modelo lee para elegir la tool."""
    async with cliente_mcp() as cliente:
        resultado = await cliente.list_tools()

    for tool in resultado.tools:
        assert tool.description, f"{tool.name} no tiene descripción"
        assert len(tool.description) > 40


@pytest.mark.asyncio
async def test_el_schema_generado_coincide_con_la_firma_de_la_funcion():
    """
    `fecha` es obligatorio y `servicio` opcional en la función Python;
    el schema que ve el cliente tiene que decir exactamente lo mismo.
    """
    async with cliente_mcp() as cliente:
        resultado = await cliente.list_tools()

    tool = next(t for t in resultado.tools if t.name == "consultar_disponibilidad")

    propiedades = tool.inputSchema["properties"]
    assert "fecha" in propiedades
    assert "servicio" in propiedades
    assert tool.inputSchema["required"] == ["fecha"]


@pytest.mark.asyncio
async def test_buscar_conocimiento_declara_top_k_como_opcional():
    async with cliente_mcp() as cliente:
        resultado = await cliente.list_tools()

    tool = next(t for t in resultado.tools if t.name == "buscar_conocimiento")

    assert tool.inputSchema["required"] == ["consulta"]
    assert "top_k" in tool.inputSchema["properties"]


# --- Ejecución real a través del protocolo ---


@pytest.mark.asyncio
async def test_llamar_consultar_disponibilidad_por_mcp_devuelve_horarios(
    base_de_prueba,
):
    async with cliente_mcp() as cliente:
        resultado = await cliente.call_tool(
            "consultar_disponibilidad", {"fecha": FECHA_STR, "servicio": "corte"}
        )

    assert not resultado.isError

    datos = json.loads(resultado.content[0].text)
    assert datos["total"] == 1
    assert datos["disponibles"][0]["hora_inicio"] == "09:00"
    # El horario_id tiene que llegar entero al otro lado del protocolo:
    # es lo que permite encadenar con crear_reservacion.
    assert isinstance(datos["disponibles"][0]["horario_id"], int)


@pytest.mark.asyncio
async def test_la_respuesta_es_serializable_a_json(base_de_prueba):
    """
    `precio` es Decimal en la base y Decimal no viaja en JSON. Si la tool
    no lo convierte, esta llamada revienta en la capa del protocolo.
    """
    async with cliente_mcp() as cliente:
        resultado = await cliente.call_tool(
            "consultar_disponibilidad", {"fecha": FECHA_STR, "servicio": "corte"}
        )

    datos = json.loads(resultado.content[0].text)
    assert datos["disponibles"][0]["precio"] == 8000.0


@pytest.mark.asyncio
async def test_encadenar_consultar_y_reservar_por_mcp(base_de_prueba):
    """
    El flujo real del agente: consulta disponibilidad, toma el horario_id
    de la respuesta, reserva con él, y el horario deja de ofrecerse. Todo
    a través del protocolo, sin tocar las funciones directamente.
    """
    async with cliente_mcp() as cliente:
        antes = json.loads(
            (
                await cliente.call_tool(
                    "consultar_disponibilidad", {"fecha": FECHA_STR}
                )
            ).content[0].text
        )
        horario_id = antes["disponibles"][0]["horario_id"]

        reserva = json.loads(
            (
                await cliente.call_tool(
                    "crear_reservacion",
                    {
                        "horario_id": horario_id,
                        "nombre_cliente": "Ana Pérez",
                        "telefono": "8888-0001",
                    },
                )
            ).content[0].text
        )

        despues = json.loads(
            (
                await cliente.call_tool(
                    "consultar_disponibilidad", {"fecha": FECHA_STR}
                )
            ).content[0].text
        )

    assert reserva["creada"] is True
    assert reserva["hora_inicio"] == "09:00"
    assert despues["total"] == antes["total"] - 1


@pytest.mark.asyncio
async def test_reservar_dos_veces_el_mismo_horario_rebota_por_mcp(base_de_prueba):
    async with cliente_mcp() as cliente:
        datos = {
            "horario_id": 1,
            "nombre_cliente": "Ana",
            "telefono": "8888-0001",
        }
        await cliente.call_tool("crear_reservacion", datos)
        segunda = json.loads(
            (
                await cliente.call_tool(
                    "crear_reservacion", {**datos, "nombre_cliente": "Luis"}
                )
            ).content[0].text
        )

    assert segunda["creada"] is False
    assert "ya fue reservado" in segunda["error"]


@pytest.mark.asyncio
async def test_reservar_y_cancelar_por_mcp_devuelve_el_horario_al_pool(base_de_prueba):
    """
    El ciclo completo a través del protocolo: se reserva el único horario,
    deja de ofrecerse, se cancela, y vuelve a estar disponible.
    """
    async with cliente_mcp() as cliente:
        reserva = json.loads(
            (
                await cliente.call_tool(
                    "crear_reservacion",
                    {
                        "horario_id": 1,
                        "nombre_cliente": "Ana Pérez",
                        "telefono": "8888-0001",
                    },
                )
            ).content[0].text
        )

        ocupado = json.loads(
            (
                await cliente.call_tool(
                    "consultar_disponibilidad", {"fecha": FECHA_STR}
                )
            ).content[0].text
        )

        cancelacion = json.loads(
            (
                await cliente.call_tool(
                    "cancelar_reservacion",
                    {"reservacion_id": reserva["reservacion_id"]},
                )
            ).content[0].text
        )

        liberado = json.loads(
            (
                await cliente.call_tool(
                    "consultar_disponibilidad", {"fecha": FECHA_STR}
                )
            ).content[0].text
        )

    assert cancelacion["cancelada"] is True
    assert cancelacion["hora_inicio"] == "09:00"
    assert ocupado["total"] == 0
    assert liberado["total"] == 1


@pytest.mark.asyncio
async def test_cancelar_solo_con_telefono_no_cancela_todavia_por_mcp(base_de_prueba):
    """
    El paso previo tiene que llegar entero al otro lado: la lista de
    reservas activas con su id, y nada cancelado.
    """
    async with cliente_mcp() as cliente:
        await cliente.call_tool(
            "crear_reservacion",
            {
                "horario_id": 1,
                "nombre_cliente": "Ana Pérez",
                "telefono": "8888-0001",
            },
        )
        resultado = json.loads(
            (
                await cliente.call_tool(
                    "cancelar_reservacion", {"telefono": "8888-0001"}
                )
            ).content[0].text
        )
        despues = json.loads(
            (
                await cliente.call_tool(
                    "consultar_disponibilidad", {"fecha": FECHA_STR}
                )
            ).content[0].text
        )

    assert resultado["cancelada"] is False
    assert resultado["requiere_confirmacion"] is True
    assert isinstance(
        resultado["reservaciones_activas"][0]["reservacion_id"], int
    )
    # Nada se canceló: el horario sigue ocupado.
    assert despues["total"] == 0


@pytest.mark.asyncio
async def test_escalar_caso_por_mcp_devuelve_numero_de_ticket(base_de_prueba):
    async with cliente_mcp() as cliente:
        resultado = await cliente.call_tool(
            "escalar_caso",
            {
                "motivo": "Le cobraron dos veces y quiere el reintegro",
                "nombre_cliente": "Ana Pérez",
                "telefono": "8888-0001",
            },
        )

    assert not resultado.isError
    datos = json.loads(resultado.content[0].text)
    assert datos["escalado"] is True
    assert datos["estado"] == "abierto"
    assert isinstance(datos["ticket_id"], int)


@pytest.mark.asyncio
async def test_escalar_caso_sin_motivo_rebota_por_mcp(base_de_prueba):
    """La tool la invoca un modelo: puede llegar con el motivo vacío."""
    async with cliente_mcp() as cliente:
        resultado = await cliente.call_tool(
            "escalar_caso", {"motivo": "   ", "nombre_cliente": "Ana"}
        )

    assert not resultado.isError
    datos = json.loads(resultado.content[0].text)
    assert datos["escalado"] is False


@pytest.mark.asyncio
async def test_un_error_de_negocio_llega_como_dato_y_no_como_excepcion(
    base_de_prueba,
):
    """
    Una fecha mal formateada no debe tumbar la llamada: el modelo tiene
    que recibir el mensaje de error para poder corregirse solo.
    """
    async with cliente_mcp() as cliente:
        resultado = await cliente.call_tool(
            "consultar_disponibilidad", {"fecha": "01/08/2026"}
        )

    assert not resultado.isError
    datos = json.loads(resultado.content[0].text)
    assert "YYYY-MM-DD" in datos["error"]
