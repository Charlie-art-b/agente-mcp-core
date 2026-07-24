#!/usr/bin/env python3
"""Test rápido de inicialización del agente"""
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
    print(f"[INFO] Modelo: {agente.modelo}")
    print("[OK] Listo para consultas")
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTest exitoso!")
