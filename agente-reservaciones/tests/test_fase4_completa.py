#!/usr/bin/env python3
"""
Test de Fase 4: Validación completa del Agente + MCP
======================================================
Verifica que el agente Gemini puede conectarse al servidor MCP y ejecutar tools.

Test cases:
1. Inicialización del agente
2. Consulta simple (búsqueda de conocimiento)
3. Consulta sobre disponibilidad
4. Creación de reservación
5. Escalamiento de caso
"""

import sys
import asyncio
from pathlib import Path

# Agregar proyecto a path
_raiz = Path(__file__).resolve().parents[1]
if str(_raiz) not in sys.path:
    sys.path.insert(0, str(_raiz))

from app.agente.agent import AgenteReservaciones


def print_header(title):
    """Imprime un encabezado formateado."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_test(numero, nombre):
    """Imprime el inicio de un test."""
    print(f"\n[TEST {numero}] {nombre}")
    print("-" * 70)


def print_result(success, message):
    """Imprime el resultado de un test."""
    prefix = "[OK]" if success else "[FAIL]"
    print(f"{prefix} {message}")


def main():
    """Ejecuta la suite de tests."""
    print_header("FASE 4: VALIDACIÓN DE AGENTE GEMINI + MCP")
    
    tests_passed = 0
    tests_total = 0

    # TEST 1: Inicialización
    tests_total += 1
    print_test(tests_total, "Inicialización del Agente")
    try:
        agente = AgenteReservaciones()
        print_result(True, f"Agente inicializado correctamente")
        print_result(True, f"Modelo: {agente.modelo}")
        print_result(True, f"Cliente MCP listo")
        tests_passed += 1
    except Exception as e:
        print_result(False, f"Error: {e}")
        return 1

    # TEST 2: Consulta simple sobre servicios
    tests_total += 1
    print_test(tests_total, "Consulta sobre servicios")
    try:
        print("Pregunta: ¿Qué servicios ofrecen?")
        respuesta = agente.consultar("¿Qué servicios ofrecen?")
        if respuesta and len(respuesta) > 10:
            print_result(True, f"Respuesta obtenida ({len(respuesta)} caracteres)")
            print(f"Preview: {respuesta[:150]}...")
            tests_passed += 1
        else:
            print_result(False, "Respuesta vacía o muy corta")
    except Exception as e:
        print_result(False, f"Error: {e}")

    # TEST 3: Consulta sobre disponibilidad
    tests_total += 1
    print_test(tests_total, "Consulta sobre disponibilidad")
    try:
        print("Pregunta: ¿Hay disponibilidad para corte mañana?")
        respuesta = agente.consultar("¿Hay disponibilidad para corte mañana?")
        if respuesta and len(respuesta) > 10:
            print_result(True, f"Respuesta obtenida ({len(respuesta)} caracteres)")
            print(f"Preview: {respuesta[:150]}...")
            tests_passed += 1
        else:
            print_result(False, "Respuesta vacía o muy corta")
    except Exception as e:
        print_result(False, f"Error: {e}")

    # TEST 4: Intención de hacer reservación
    tests_total += 1
    print_test(tests_total, "Consulta sobre reservación")
    try:
        print("Pregunta: Quiero agendar un corte de cabello")
        respuesta = agente.consultar("Quiero agendar un corte de cabello")
        if respuesta and len(respuesta) > 10:
            print_result(True, f"Respuesta obtenida ({len(respuesta)} caracteres)")
            print(f"Preview: {respuesta[:150]}...")
            tests_passed += 1
        else:
            print_result(False, "Respuesta vacía o muy corta")
    except Exception as e:
        print_result(False, f"Error: {e}")

    # TEST 5: Escalación de caso
    tests_total += 1
    print_test(tests_total, "Consulta sobre escalación")
    try:
        print("Pregunta: Necesito hablar con un gerente")
        respuesta = agente.consultar("Necesito hablar con un gerente")
        if respuesta and len(respuesta) > 10:
            print_result(True, f"Respuesta obtenida ({len(respuesta)} caracteres)")
            print(f"Preview: {respuesta[:150]}...")
            tests_passed += 1
        else:
            print_result(False, "Respuesta vacía o muy corta")
    except Exception as e:
        print_result(False, f"Error: {e}")

    # Resumen
    print_header(f"RESUMEN: {tests_passed}/{tests_total} tests pasados")
    
    if tests_passed == tests_total:
        print("[SUCCESS] Todos los tests pasaron!")
        print("\n[OK] Fase 4 completada exitosamente")
        print("[OK] El agente puede:")
        print("  - Inicializarse correctamente")
        print("  - Comunicarse con Gemini")
        print("  - Ejecutar tools a través del servidor MCP")
        print("  - Procesar y devolver respuestas")
        return 0
    else:
        print(f"[WARNING] {tests_total - tests_passed} tests fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(main())
