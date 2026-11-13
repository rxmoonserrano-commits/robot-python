"""Reporte semanal: lunes 08:00, por correo. Nunca manda WhatsApp.

Lee los últimos 7 días de Conversaciones y Clientes, cuenta con
logic.contar_semana (los números salen de las hojas, no se inventan),
Gemini escribe un resumen limpio con una idea útil y una sugerencia,
se manda por Gmail al dueño y se guarda una fila en la pestaña Reporte.
Si no hay datos, los contadores salen en cero y el correo lo dice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import settings
from .gemini import generar_texto
from .logic import contar_semana
from .mail import enviar_correo
from .sheets import guardar_reporte, leer_pestana


def generar_reporte_semanal() -> dict:
    """Hace el reporte de los últimos 7 días y lo manda. Devuelve los contadores."""
    hasta = datetime.now(timezone.utc)
    desde = hasta - timedelta(days=7)
    conversaciones = leer_pestana("Conversaciones")
    clientes = leer_pestana("Clientes")
    conteo = contar_semana(conversaciones, clientes, desde, hasta)

    semana = f"{desde.date()} a {hasta.date()}"
    motivos = (
        ", ".join(f"{m} ({n})" for m, n in conteo["motivos_top"])
        or "sin motivos registrados"
    )
    # (v3.0) json_mode=False: el resumen es PROSA, no JSON. En la v2.13
    # generar_texto pedía JSON siempre y el correo del lunes llegaba
    # con el texto envuelto en llaves.
    resumen = generar_texto(
        "Escribe un resumen semanal corto y elegante para el dueño de un negocio, "
        "en español, con calma y sin exagerar. Usa SOLO estos datos, no inventes nada. "
        "Termina con una idea útil y una sugerencia para la próxima semana.\n\n"
        f"Semana: {semana}\n"
        f"Mensajes atendidos por el robot: {conteo['mensajes_atendidos']}\n"
        f"Clientes calificados: {conteo['clientes_calificados']}\n"
        f"Citas agendadas: {conteo['citas_agendadas']}\n"
        f"Casos pasados a una persona: {conteo['handoffs']}\n"
        f"Mensajes sin responder porque una persona atendía: {conteo['sin_respuesta_por_humano']}\n"
        f"Motivos más comunes: {motivos}",
        json_mode=False,
    )

    cuerpo = (
        f"Reporte semanal del robot — {semana}\n\n"
        f"Mensajes atendidos: {conteo['mensajes_atendidos']}\n"
        f"Clientes calificados: {conteo['clientes_calificados']}\n"
        f"Citas agendadas: {conteo['citas_agendadas']}\n"
        f"Casos pasados a una persona: {conteo['handoffs']}\n"
        f"Mensajes sin responder (humano atendiendo): {conteo['sin_respuesta_por_humano']}\n"
        f"Motivos más comunes: {motivos}\n\n"
        f"{resumen}\n"
    )
    enviar_correo(settings.owner_email, f"Reporte semanal del robot — {semana}", cuerpo)
    guardar_reporte(
        semana,
        conteo["mensajes_atendidos"],
        conteo["clientes_calificados"],
        conteo["citas_agendadas"],
        conteo["handoffs"],
        resumen,
    )
    return {"semana": semana, **conteo, "resumen": resumen}
