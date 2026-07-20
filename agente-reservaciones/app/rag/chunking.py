"""
Chunking
========
Divide documentos largos en fragmentos (chunks) más pequeños, que es lo
que realmente se guarda y se busca en el vector store. Un chunk debe ser
lo suficientemente pequeño para ser específico, pero lo suficientemente
grande para tener contexto completo.

Estrategia usada: chunking por párrafos con solapamiento (overlap) de
oraciones, para no cortar ideas a la mitad.
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    texto: str
    fuente: str
    indice: int


def dividir_en_chunks(
    texto: str,
    fuente: str,
    max_caracteres: int = 500,
    solapamiento: int = 80,
) -> list[Chunk]:
    """
    Divide un texto en chunks de tamaño máximo `max_caracteres`,
    con `solapamiento` caracteres compartidos entre chunks consecutivos
    para no perder contexto en los bordes.
    """
    texto = texto.strip()
    if not texto:
        return []

    chunks: list[Chunk] = []
    inicio = 0
    indice = 0

    while inicio < len(texto):
        fin = min(inicio + max_caracteres, len(texto))

        # Evitar cortar una palabra a la mitad: retroceder hasta el
        # último espacio dentro del rango, si no estamos en el final.
        if fin < len(texto):
            ultimo_espacio = texto.rfind(" ", inicio, fin)
            if ultimo_espacio > inicio:
                fin = ultimo_espacio

        fragmento = texto[inicio:fin].strip()
        if fragmento:
            chunks.append(Chunk(texto=fragmento, fuente=fuente, indice=indice))
            indice += 1

        if fin >= len(texto):
            break

        inicio = fin - solapamiento if fin - solapamiento > inicio else fin

    return chunks
