#!/usr/bin/env python3
"""
Verificar Setup de Fase 4
==========================
Verifica que todas las dependencias y configuraciones están en lugar para ejecutar la Fase 4.
"""

import os
import sys
from pathlib import Path

# Agregar raíz a path
_RAIZ = Path(__file__).resolve().parents[1]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


def verificar_imports():
    """Verifica que las librerías requeridas estén instaladas."""
    print("Verificando imports...")
    imports_requeridos = [
        ("google.genai", "google-genai (Gemini API)"),
        ("mcp.client.stdio", "mcp (Model Context Protocol)"),
        ("fastapi", "fastapi"),
        ("pydantic", "pydantic"),
        ("sqlalchemy", "sqlalchemy"),
    ]

    todos_ok = True
    for modulo, nombre in imports_requeridos:
        try:
            __import__(modulo)
            print(f"  ✓ {nombre}")
        except ImportError as e:
            print(f"  ✗ {nombre} - NO INSTALADO")
            print(f"     Error: {e}")
            todos_ok = False

    return todos_ok


def verificar_env():
    """Verifica que las variables de entorno necesarias estén configuradas."""
    print("\nVerificando .env...")

    env_requerido = [
        ("GEMINI_API_KEY", "API Key de Gemini (https://aistudio.google.com/apikey)"),
        ("GEMINI_MODEL", "Modelo de Gemini a usar"),
        ("DATABASE_URL", "URL de conexión a PostgreSQL"),
    ]

    todos_ok = True
    for var, descripcion in env_requerido:
        valor = os.getenv(var)
        if valor:
            # Mostrar solo los primeros caracteres de keys sensibles
            if "KEY" in var:
                valor_mostrado = valor[:10] + "..." if len(valor) > 10 else valor
            else:
                valor_mostrado = valor
            print(f"  ✓ {var}={valor_mostrado}")
        else:
            print(f"  ✗ {var} - NO CONFIGURADO")
            print(f"     ({descripcion})")
            todos_ok = False

    return todos_ok


def verificar_archivos():
    """Verifica que los archivos necesarios existan."""
    print("\nVerificando archivos...")

    archivos_requeridos = [
        ("app/agente/__init__.py", "Módulo agente"),
        ("app/agente/agent.py", "Agente principal"),
        ("app/agente/cliente_mcp.py", "Cliente MCP"),
        ("app/main.py", "Servidor FastAPI"),
        ("app/mcp_server/server.py", "Servidor MCP"),
        ("tests/test_agente.py", "Test interactivo del agente"),
        ("data/documents/ejemplo_prueba.md", "Documentos de conocimiento"),
    ]

    todos_ok = True
    for archivo, descripcion in archivos_requeridos:
        ruta = _RAIZ / archivo
        if ruta.exists():
            print(f"  ✓ {archivo}")
        else:
            print(f"  ✗ {archivo} - NO ENCONTRADO ({descripcion})")
            todos_ok = False

    return todos_ok


def verificar_db():
    """Verifica que PostgreSQL esté disponible."""
    print("\nVerificando base de datos...")

    try:
        from app.db.session import obtener_sesion

        sesion = obtener_sesion()
        sesion.execute("SELECT 1")
        sesion.close()
        print("  ✓ PostgreSQL disponible")
        return True

    except Exception as e:
        print(f"  ✗ PostgreSQL NO disponible")
        print(f"     Error: {e}")
        print(f"     Ejecuta: docker compose up -d postgres")
        return False


def verificar_vector_store():
    """Verifica que el vector store esté poblado."""
    print("\nVerificando vector store (RAG)...")

    try:
        from app.rag.store import VectorStore

        store = VectorStore()
        count = store.contar()

        if count > 0:
            print(f"  ✓ Vector store listo ({count} documentos)")
            return True
        else:
            print(f"  ✗ Vector store VACÍO")
            print(f"     Ejecuta: python -m app.rag.ingest")
            return False

    except Exception as e:
        print(f"  ✗ Vector store NO disponible")
        print(f"     Error: {e}")
        return False


def main():
    """Ejecuta todas las verificaciones."""
    print("=" * 70)
    print("VERIFICACIÓN DE SETUP - FASE 4")
    print("=" * 70)

    resultados = {
        "imports": verificar_imports(),
        "env": verificar_env(),
        "archivos": verificar_archivos(),
        "db": verificar_db(),
        "vector_store": verificar_vector_store(),
    }

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)

    if all(resultados.values()):
        print("✓ Todo está listo para ejecutar la Fase 4!")
        print("\nPara probar, ejecuta:")
        print("  python tests/test_agente.py")
        print("\nO levanta el servidor HTTP:")
        print("  python -m uvicorn app.main:app --reload --port 8000")
        return 0

    else:
        problemas = [k for k, v in resultados.items() if not v]
        print(f"✗ Hay {len(problemas)} problema(s):")
        for problema in problemas:
            print(f"  - {problema}")

        print("\nRevisá los errores arriba y ejecutá los comandos sugeridos.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
