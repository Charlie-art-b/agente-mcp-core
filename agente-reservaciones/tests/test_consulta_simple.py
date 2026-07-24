#!/usr/bin/env python3
"""Test de consulta simple con el agente"""
import sys
from pathlib import Path

# Agregar proyecto a path
_raiz = Path(__file__).resolve().parents[1]
if str(_raiz) not in sys.path:
    sys.path.insert(0, str(_raiz))

print("1. Importando AgenteReservaciones...")
from app.agente.agent import AgenteReservaciones

print("2. Inicializando agente...")
try:
    agente = AgenteReservaciones()
    print("[OK] Agente inicializado")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

print("\n3. Haciendo una consulta de prueba...")
print("   Pregunta: ¿Qué servicios ofrecen?")
try:
    respuesta = agente.consultar("¿Qué servicios ofrecen?")
    print(f"\n[OK] Respuesta recibida:")
    print(f"   {respuesta[:200]}..." if len(respuesta) > 200 else f"   {respuesta}")
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[SUCCESS] Test completado exitosamente!")
