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
from .logic import _DIAS_NOMBRE, _MESES, contar_semana, formatear_cita_bonita
from .mail import enviar_correo
from .negocio import correo_dueno, funcion_activa, nombre_negocio
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


def _fecha_corta(valor: str) -> str:
    """Fecha corta legible (dd/mm hh:mm) desde un ISO; si no, el texto tal cual."""
    try:
        fecha = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        local = fecha.astimezone(ZoneInfo("America/Mazatlan"))
        return local.strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return str(valor or "")[:16]


def generar_reporte_semanal() -> dict:
    """Hace el reporte de los últimos 7 días y lo manda. Devuelve los contadores.

    (v3.7) Los TRES tipos de alerta del dueño en UN solo correo
    semanal, estilo "reporte de valor" (lo que Jose pidió del chat
    de ChatGPT): citas confirmadas, necesitaron humano, y resumen
    con números que prueban el valor. Sin avalancha de correos: el
    dueño ve todo el lunes a las 08:00, sin entrar a ningún lado.
    Los números salen de las hojas; lo estimado va marcado como
    estimado. Paquete básico: sin reportes, se omite sin mandar nada.
    """
    if not funcion_activa("reportes"):
        return {"omitido": True, "motivo": "paquete sin reportes"}
    hasta = datetime.now(timezone.utc)
    desde = hasta - timedelta(days=7)
    conversaciones = leer_pestana("Conversaciones")
    clientes = leer_pestana("Clientes")
    conteo = contar_semana(conversaciones, clientes, desde, hasta)

    # Tipo 1: citas confirmadas esta semana (lista con fecha bonita).
    citas = [
        f for f in clientes
        if _en_ventana(f, desde, hasta)
        and str(f.get("estatus", "")).strip() == "agendado"
        and str(f.get("fecha_cita", "")).strip()
    ]
    # Tipo 2: necesitaron atención humana esta semana.
    humanos = [
        f for f in clientes
        if _en_ventana(f, desde, hasta)
        and str(f.get("handoff", "")).strip().lower() == "si"
    ]
    # Por recuperar: preguntaron (tienen motivo), no agendaron, sin
    # cita y nadie los está atendiendo (sin handoff). Uno por
    # teléfono (el último registro manda).
    por_recuperar: dict[str, dict] = {}
    for f in clientes:
        if (
            _en_ventana(f, desde, hasta)
            and str(f.get("estatus", "")).strip() == "en conversacion"
            and not str(f.get("fecha_cita", "")).strip()
            and str(f.get("motivo", "")).strip()
            and str(f.get("handoff", "")).strip().lower() != "si"
        ):
            por_recuperar[str(f.get("telefono", "")).strip()] = f
    recuperar = list(por_recuperar.values())

    # Métricas de valor: confirmados vs estimados, sin inventar.
    atendidos = conteo["mensajes_atendidos"]
    handoffs_n = conteo["handoffs"]
    resueltas = max(atendidos - handoffs_n, 0)
    pct = round(100 * resueltas / atendidos) if atendidos else 0
    horas = resueltas * 5 / 60
    sin_respuesta = sum(
        1 for f in conversaciones
        if _en_ventana(f, desde, hasta)
        and str(f.get("robot_respondio", "")).strip() == "no"
    )

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

    nombre_neg = nombre_negocio() or "tu negocio"
    if citas:
        lineas_citas = "\n".join(
            f"- {f.get('nombre') or f.get('telefono')} — {f.get('motivo') or 'cita'}"
            f" — {formatear_cita_bonita(str(f.get('fecha_cita', '')))}"
            for f in citas
        )
    else:
        lineas_citas = "Ninguna esta semana."
    if humanos:
        lineas_humanos = "\n".join(
            f"- {f.get('nombre') or f.get('telefono')} — {f.get('motivo') or 'sin motivo'}"
            f" ({_fecha_corta(str(f.get('fecha', '')))})"
            for f in humanos
        )
    else:
        lineas_humanos = "Ninguna esta semana."
    if recuperar:
        lineas_recuperar = "\n".join(
            f"- {f.get('nombre') or f.get('telefono')} preguntó por {f.get('motivo')}."
            f" Borrador listo para copiar: \"Hola {f.get('nombre') or ''}, vi que"
            f" preguntaste por {f.get('motivo')}. ¿Te aparto un lugar esta semana?\""
            for f in recuperar
        )
    else:
        lineas_recuperar = "Nadie por recuperar esta semana."

    cuerpo = (
        f"Tu semana en {nombre_neg} — {semana}\n\n"
        "Aquí está tu semana, sin que tengas que entrar a ningún lado.\n\n"
        f"📅 CITAS CONFIRMADAS ({len(citas)})\n{lineas_citas}\n\n"
        f"🙋 NECESITARON ATENCIÓN HUMANA ({len(humanos)})\n{lineas_humanos}\n\n"
        f"💬 CLIENTES POR RECUPERAR ({len(recuperar)})\n{lineas_recuperar}\n\n"
        "📊 TU SEMANA EN NÚMEROS\n"
        f"- Conversaciones atendidas: {atendidos}\n"
        f"- Resueltas sin pasar a humano: {resueltas} ({pct}%)\n"
        f"- Citas confirmadas: {conteo['citas_agendadas']}\n"
        f"- Clientes atendidos: {conteo['clientes_calificados']}\n"
        f"- Tiempo ahorrado estimado: ~{horas:.1f} h"
        " (5 min por conversación resuelta)\n"
        f"- Mensajes sin respuesta del robot: {sin_respuesta}"
        " (todos quedaron registrados en la hoja)\n\n"
        f"{resumen}\n"
    )
    enviar_correo(
        correo_dueno(),
        f"Tu semana en {nombre_neg} — citas, humanos y resumen",
        cuerpo,
    )
    guardar_reporte(
        semana,
        conteo["mensajes_atendidos"],
        conteo["clientes_calificados"],
        conteo["citas_agendadas"],
        conteo["handoffs"],
        resumen,
    )
    return {"semana": semana, **conteo, "resumen": resumen}
