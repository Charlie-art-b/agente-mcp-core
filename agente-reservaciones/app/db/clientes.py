"""
Operaciones sobre clientes
===========================
Lo que varias tools necesitan hacer con la ficha del cliente. Vive acá y
no dentro de una tool porque tanto `crear_reservacion` como
`escalar_caso` tienen que resolver lo mismo: la persona que escribe puede
ser nueva o puede haber pasado antes.
"""

from app.db.models import Cliente


def buscar_o_crear_cliente(
    sesion,
    nombre: str,
    telefono: str | None = None,
    email: str | None = None,
) -> Cliente:
    """
    Devuelve el cliente que corresponde a ese teléfono, creándolo si no
    existe todavía.

    El teléfono es la única forma de reconocer a alguien (es la columna
    única del esquema). Si no viene, se crea una ficha nueva cada vez: no
    hay manera de saber si es la misma persona de antes.
    """
    if telefono:
        existente = sesion.query(Cliente).filter_by(telefono=telefono).first()
        if existente is not None:
            return existente

    cliente = Cliente(nombre=nombre, telefono=telefono, email=email)
    sesion.add(cliente)
    sesion.flush()  # para que tenga id antes de referenciarlo
    return cliente
