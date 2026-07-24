#!/usr/bin/env python3
"""
Instrucciones para Fase 5: Evaluación y Logging
================================================

Fase 4 está COMPLETADA. El agente Gemini + MCP está funcionando correctamente.

PRÓXIMAS TAREAS (Fase 5):

1. EVALUACIÓN
   - Crear dataset de test cases conocidos
   - Medir si el agente selecciona las tools correctas
   - Medir latencia y costo de cada consulta
   - Medir satisfacción de respuestas (manual o con modelo evaluador)

2. LOGGING
   - Registrar cada consulta: pregunta, tool ejecutada, resultado, tiempo
   - Crear dashboard de métricas
   - Identificar casos donde el agente falla

3. OPTIMIZACIÓN
   - Mejorar prompts basado en resultados
   - Ajustar definiciones de tools si es necesario
   - Fine-tuning de parámetros de Gemini

4. PRODUCCIÓN
   - Preparar para scaling
   - Implementar rate limiting
   - Agregar autenticación si es necesario
   - Deploy a servidor

CÓMO PROCEDER:

1. Revisar el código actual
   - AgenteReservaciones en app/agente/agent.py
   - ClienteMCP en app/agente/cliente_mcp.py
   - API en app/main.py

2. Crear dataset de evaluación
   - 50+ preguntas sobre servicios, disponibilidad, reservaciones, escalación
   - Cada una con respuesta esperada y tool que debería ejecutarse

3. Implementar harness de evaluación
   - Ejecutar cada pregunta del dataset
   - Registrar qué tool se ejecutó
   - Comparar con resultado esperado
   - Calcular accuracy

4. Agregar logging
   - Estructura de logs consistente (JSON)
   - Guardar en archivo o base de datos
   - Incluir: timestamp, user_id, pregunta, tool, resultado, tiempo, costo

5. Crear dashboard
   - Gráficos de accuracy por tipo de consulta
   - Latencia promedio por tool
   - Costo total diario/mensual
   - Casos de falla más comunes

ARCHIVOS IMPORTANTES:

- app/agente/agent.py: Lógica del agente
- app/agente/cliente_mcp.py: Cliente MCP
- app/main.py: API FastAPI
- tests/test_fase4_completa.py: Tests validados
- FASE_4_STATUS.md: Estado actual
- FASE4_COMPLETADA.md: Documentación detallada

COMANDOS ÚTILES:

# Ejecutar tests de Fase 4
python tests/test_fase4_completa.py

# Ejecutar modo interactivo
python tests/test_agente.py

# Iniciar API
python -m app.main

# Ver logs del servidor
python -m app.mcp_server.server

RECOMENDACIONES PARA FASE 5:

1. NO modificar el core del agente (está funcionando bien)
2. Agregar capas de logging/evaluación sin tocar la lógica
3. Crear módulos separados para evaluación y métricas
4. Mantener tests pasando en cada cambio
5. Documentar decisiones en ADRs (Architecture Decision Records)

¡FASE 4 COMPLETADA CON ÉXITO!

Próximo paso: Fase 5 - Evaluación y Optimización
"""

if __name__ == "__main__":
    print(__doc__)
