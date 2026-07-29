"""
Precios del modelo
==================
Un solo lugar para la tarifa de tokens, que usan tanto la evaluación de
costo (app/eval) como el logging (app/logging). Así no se duplica el número.

⚠️ Son valores de REFERENCIA. Verificá el precio actual del modelo que uses
en https://ai.google.dev/pricing y ajustá acá. Los tokens son exactos; el
costo es tan preciso como esta tarifa.
"""

# Dólares por millón de tokens.
PRECIO_ENTRADA_POR_1M = 0.10
PRECIO_SALIDA_POR_1M = 0.40


def costo_de_tokens(tokens_entrada: int, tokens_salida: int) -> float:
    """Costo en dólares de una cantidad de tokens de entrada y salida."""
    return (
        tokens_entrada / 1_000_000 * PRECIO_ENTRADA_POR_1M
        + tokens_salida / 1_000_000 * PRECIO_SALIDA_POR_1M
    )
