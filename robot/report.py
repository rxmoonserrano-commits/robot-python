"""Reporte semanal: lunes 08:00, por correo. Nunca manda WhatsApp.

Lee los últimos 7 días de Conversaciones y Clientes, cuenta con
logic.contar_semana (los números salen de las hojas, no se inventan),
Gemini escribe un resumen limpio con una idea útil y una sugerencia,
se manda por Gmail al dueño y se guarda una fila en la pestaña Reporte.
Si no hay datos, los contadores salen en cero y el correo lo dice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .gemini import generar_texto
from .logic import _DIAS_NOMBRE, _MESES, contar_semana
from .mail import enviar_correo
from .negocio import funcion_activa
from .sheets import guardar_reporte, leer_pestana, leer_propuestas


def _en_ventana(fila: dict, desde: datetime, hasta: datetime) -> bool:
    """¿La fecha de la fila cae en la ventana? (mismo criterio que contar_semana)."""
    try:
        fecha = datetime.fromisoformat(str(fila.get("fecha", "")).replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return desde <= fecha < hasta
    except ValueError:
        return False


def _en_ventana_texto(valor: str, desde: datetime, hasta: datetime) -> bool:
    """Como _en_ventana, pero el valor viene suelto (creado_en de Propuestas)."""
    try:
        fecha = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return desde <= fecha < hasta
    except ValueError:
        return False


def generar_resumen_manana() -> dict:
    """Resumen de la mañana: qué pasó en las últimas 24 h, por correo.

    Lo que el dueño quiere al despertar: cuántos escribieron, quiénes
    son nuevos, qué citas se agendaron, quién necesita una persona HOY
    y qué citas tiene hoy. Sin IA: son números y listas de la hoja, no
    un resumen inventado. No guarda fila en Reporte (esa pestaña es
    semanal). Devuelve los contadores y las listas.
    Sin Gmail, el correo no sale (igual que el semanal) y eso queda en
    el registro del trabajo programado.

    (v3.6) Paquete básico: sin reportes. Se omite sin mandar nada.
    """
    if not funcion_activa("reportes"):
        return {"omitido": True, "motivo": "paquete sin reportes"}
    hasta = datetime.now(timezone.utc)
    desde = hasta - timedelta(hours=24)
    conversaciones = leer_pestana("Conversaciones")
    clientes = leer_pestana("Clientes")
    conteo = contar_semana(conversaciones, clientes, desde, hasta)

    local_hoy = hasta.astimezone(ZoneInfo(settings.timezone))
    fecha_bonita = (
        f"{_DIAS_NOMBRE[local_hoy.weekday()]} {local_hoy.day} de "
        f"{_MESES[local_hoy.month - 1]}"
    )
    # Pendientes: clientes con handoff="si" en las últimas 24 h.
    pendientes = [
        f"{str(c.get('nombre') or c.get('telefono', '')).strip()} "
        f"({str(c.get('telefono', '')).strip()}): "
        f"{str(c.get('motivo') or 'necesita una persona').strip()}"
        for c in clientes
        if str(c.get("handoff", "")).strip().lower() == "si"
        and _en_ventana(c, desde, hasta)
    ]
    # Propuestas sin contestar (creadas en las últimas 24 h).
    propuestas = []
    for p in leer_propuestas():
        if not _en_ventana_texto(str(p.get("creado_en", "")), desde, hasta):
            continue
        linea = (
            f"{str(p.get('nombre') or p.get('telefono', '')).strip()} "
            f"({str(p.get('telefono', '')).strip()}): "
            f"{str(p.get('motivo') or 'cita').strip()}, "
            f"{str(p.get('fecha_bonita') or '').strip()}"
        )
        if str(p.get("apartado", "")).strip().lower() == "si":
            linea += f" (apartado hasta {str(p.get('aparta_hasta', '')).strip()})"
        propuestas.append(linea)
    # Citas de hoy: agendadas y con fecha_cita en la fecha local de hoy.
    citas_hoy = []
    for c in clientes:
        if str(c.get("estatus", "")).strip() != "agendado":
            continue
        try:
            fecha_cita = datetime.fromisoformat(
                str(c.get("fecha_cita", "")).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if fecha_cita.tzinfo is None:
            fecha_cita = fecha_cita.replace(tzinfo=ZoneInfo(settings.timezone))
        fecha_local = fecha_cita.astimezone(ZoneInfo(settings.timezone))
        if fecha_local.date() != local_hoy.date():
            continue
        citas_hoy.append(
            f"{str(c.get('nombre') or c.get('telefono', '')).strip()} "
            f"({str(c.get('telefono', '')).strip()}): "
            f"{str(c.get('motivo') or 'cita').strip()}, "
            f"{fecha_local:%H:%M}"
        )

    def _bloque(titulo: str, lineas: list[str]) -> str:
        if not lineas:
            return f"{titulo}: ninguno.\n"
        return f"{titulo}:\n" + "".join(f"- {l}\n" for l in lineas)

    cuerpo = (
        f"Resumen de la mañana — {fecha_bonita}\n\n"
        "Anoche (últimas 24 h):\n"
        f"Mensajes atendidos: {conteo['mensajes_atendidos']}\n"
        f"Clientes nuevos: {conteo['clientes_calificados']}\n"
        f"Citas agendadas: {conteo['citas_agendadas']}\n"
        f"Casos pasados a una persona: {conteo['handoffs']}\n\n"
        + _bloque("Pendientes para hoy (necesitan una persona)", pendientes)
        + "\n"
        + _bloque("Propuestas sin contestar", propuestas)
        + "\n"
        + _bloque(f"Citas de hoy ({fecha_bonita})", citas_hoy)
    )
    enviar_correo(settings.owner_email, f"Resumen de la mañana — {fecha_bonita}", cuerpo)
    return {
        "fecha": fecha_bonita,
        **conteo,
        "pendientes": pendientes,
        "propuestas": propuestas,
        "citas_hoy": citas_hoy,
    }


def generar_reporte_semanal() -> dict:
    """Hace el reporte de los últimos 7 días y lo manda. Devuelve los contadores.

    (v3.6) Paquete básico: sin reportes. Se omite sin mandar nada.
    """
    if not funcion_activa("reportes"):
        return {"omitido": True, "motivo": "paquete sin reportes"}
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
