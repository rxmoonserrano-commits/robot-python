"""Manda el reporte semanal ahora, sin esperar al lunes.

Uso:  python reporte_semanal.py

Hace lo mismo que el trabajo programado de los lunes 08:00:
lee los últimos 7 días, cuenta, Gemini escribe el resumen,
lo manda por Gmail al dueño y guarda una fila en la pestaña Reporte.
"""

from robot.report import generar_reporte_semanal

if __name__ == "__main__":
    resultado = generar_reporte_semanal()
    print(f"Reporte enviado: {resultado['semana']}")
    print(f"  Mensajes atendidos: {resultado['mensajes_atendidos']}")
    print(f"  Clientes calificados: {resultado['clientes_calificados']}")
    print(f"  Citas agendadas: {resultado['citas_agendadas']}")
    print(f"  Handoffs: {resultado['handoffs']}")
    print(f"  Sin respuesta por humano atendiendo: {resultado['sin_respuesta_por_humano']}")
