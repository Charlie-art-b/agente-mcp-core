"""
Test de la Fase 4: Agente Gemini + MCP
========================================
Verifica que el agente Gemini puede conectarse al servidor MCP y ejecutar tools.

Este test es manual (no parametrizado con pytest) porque interactúa con APIs
externas (Gemini) y porque el output es interactivo. Se ejecuta así:

    python tests/test_agente.py

Para que funcione necesita:
- GEMINI_API_KEY en .env
- Servidor Postgres funcionando (sqlite en memory NO sirve para este test)
- Base de datos poblada con datos de ejemplo (python -m app.db.seed)
- Vector store de Chroma poblado (python -m app.rag.ingest)
"""

import sys
from pathlib import Path

# Asegurar que el proyecto esté en path
_raiz = Path(__file__).resolve().parents[1]
if str(_raiz) not in sys.path:
    sys.path.insert(0, str(_raiz))

from app.agente.agent import AgenteReservaciones


def main():
    """Corre el agente en modo interactivo."""
    print("\n" + "=" * 70)
    print("AGENTE DE RESERVACIONES - FASE 4")
    print("=" * 70)
    print("\nBienvenido al agente de reservaciones.")
    print("Escribe tus preguntas en lenguaje natural.")
    print("Para salir, escribe 'salir' o presiona Ctrl+C.\n")

    try:
        agente = AgenteReservaciones()
        print("[OK] Agente inicializado correctamente")
        print("[OK] Cliente MCP conectado\n")

    except Exception as e:
        print(f"[ERROR] Error al inicializar el agente: {e}")
        print("\nVerifica que:")
        print("  1. GEMINI_API_KEY está en .env")
        print("  2. PostgreSQL está funcionando")
        print("  3. La BD está poblada: python -m app.db.seed")
        print("  4. El vector store está listo: python -m app.rag.ingest")
        return 1

    # Loop de conversación
    #
    # NOTA: el `try/finally` de acá afuera asegura que agente.cerrar() se
    # llame UNA SOLA VEZ al terminar toda la conversación (sin importar si
    # se sale escribiendo "salir", con Ctrl+C, o por cualquier excepción no
    # controlada), y no después de cada pregunta individual. Antes el
    # cliente MCP se cerraba (y por lo tanto el subprocess del servidor se
    # relanzaba desde cero) en cada turno, lo cual era costoso y causaba
    # fallas intermitentes en la primera consulta de una sesión.
    try:
        while True:
            try:
                pregunta = input("\nTú: ").strip()

                if not pregunta:
                    continue

                if pregunta.lower() in ["salir", "exit", "quit"]:
                    print("\n¡Hasta luego!")
                    break

                print("\nAgente: [procesando...]")

                respuesta = agente.consultar(pregunta)

                print(f"\nAgente: {respuesta}")

            except KeyboardInterrupt:
                print("\n\nHasta luego!")
                break
            except Exception as e:
                print(f"\n[ERROR] Error: {e}")
                print("(continuando...)\n")
    finally:
        agente.cerrar()

    return 0


if __name__ == "__main__":
    sys.exit(main())