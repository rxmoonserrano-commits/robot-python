"""Reporte semanal: lunes 08:00, por correo. Nunca manda WhatsApp.

Lee los últimos 7 días de Conversaciones y Clientes, cuenta con
logic.contar_semana (los números salen de las hojas, no se inventan),
Gemini escribe un resumen limpio con una idea útil y una sugerencia,
se manda por Gmail al dueño y se guarda una fila en la pestaña Reporte.
Si no hay datos, los contadores salen en cero y el correo lo dice.
"""

from __future__ import annotations

import html as _html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .gemini import generar_texto
from .logic import (
    _DIAS_NOMBRE,
    _MESES,
    contar_semana,
    formatear_cita_bonita,
    horarios_por_dia,
)
from .mail import enviar_correo
from .negocio import correo_dueno, funcion_activa, nombre_negocio
from .revision import _montos_en_texto
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


# --- Métricas de retorno (v3.20.5, auditoría de negocio) -------------------
# Lo que el cliente que paga quiere ver el lunes: cuánto valen las
# citas que le trajo el robot, qué atendió de noche, a quiénes
# recuperó y si va mejor que la semana pasada. Todo sale de las
# hojas; lo que no se puede comprobar NO se afirma (None = sin dato,
# y la línea simplemente no sale en el correo).


def _normalizar(texto: str) -> str:
    """Sin acentos, minúsculas, espacios simples (para cruzar el
    motivo de la cita con el servicio de Conocimiento)."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def _precio_servicio(motivo: str, conocimiento: list[dict]) -> int | None:
    """Precio de un servicio desde Conocimiento, o None si no hay
    coincidencia clara (sin servicio, sin precio, o precio ambiguo
    con varios montos distintos en la fila). Determinista: nunca
    adivina.

    (v3.20.6) Si el motivo cruza con VARIOS servicios de precios
    distintos (p. ej. "dental" cruza con "Limpieza dental" y con
    "Blanqueamiento dental"), no hay coincidencia clara: None.
    Antes se tomaba el primer servicio y el reporte sumaba un
    precio que podía no ser el de esa cita.
    """
    objetivo = _normalizar(motivo)
    if not objetivo:
        return None
    precios: set[int] = set()
    for f in conocimiento or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("tipo", "")).strip().lower() != "servicio":
            continue
        nombre = _normalizar(f.get("pregunta_o_servicio", ""))
        if not nombre or not (objetivo in nombre or nombre in objetivo):
            continue
        montos = set(_montos_en_texto(" ".join(
            str(v) for v in f.values() if isinstance(v, str))))
        if len(montos) == 1:
            precios.add(next(iter(montos)))
        # Fila ambigua (varios montos) o sin precio: no aporta,
        # pero no descarta las demás coincidencias.
    if len(precios) == 1:
        return next(iter(precios))
    return None  # sin coincidencia clara: no se adivina


def valor_estimado_citas(citas: list[dict],
                         conocimiento: list[dict]) -> tuple[int, int, int]:
    """Valor estimado en pesos de las citas confirmadas, desde los
    precios de Conocimiento. Devuelve (total, n_con_precio, n_sin).
    Lo que no cruza con un precio conocido NO se suma: el reporte
    nunca inventa pesos."""
    total = 0
    con = 0
    sin = 0
    for f in citas:
        precio = _precio_servicio(str(f.get("motivo") or ""), conocimiento)
        if precio is None:
            sin += 1
        else:
            total += precio
            con += 1
    return total, con, sin


def conversaciones_fuera_de_horario(conversaciones: list[dict],
                                    conocimiento: list[dict],
                                    desde: datetime,
                                    hasta: datetime) -> int | None:
    """Cuántas conversaciones atendió el robot fuera del horario del
    negocio (el cliente escribió y el robot respondió estando
    cerrado). None si el negocio no tiene horario en Conocimiento:
    sin dato no se afirma nada."""
    horarios = horarios_por_dia(conocimiento)
    if not horarios:
        return None
    tz = ZoneInfo(settings.timezone)
    n = 0
    for f in conversaciones:
        if f.get("quien_hablo") != "cliente":
            continue
        if str(f.get("robot_respondio", "")).strip() != "si":
            continue
        try:
            fecha = datetime.fromisoformat(str(f.get("fecha", "")).replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (desde <= fecha < hasta):
            continue
        local = fecha.astimezone(tz)
        horas = horarios.get(local.weekday())
        if horas is None:
            n += 1  # ese día el negocio no abre
        else:
            minutos = local.hour * 60 + local.minute
            if not (horas[0] <= minutos < horas[1]):
                n += 1
    return n


def clientes_que_volvieron(clientes: list[dict], conversaciones: list[dict],
                           desde: datetime, hasta: datetime) -> int:
    """Clientes que agendaron en la ventana pero ya habían escrito
    ANTES de ella: el robot recuperó a alguien que ya se había ido.
    Determinista: teléfono con conversación previa a la ventana."""
    primeras: dict[str, datetime] = {}
    for f in conversaciones:
        tel = str(f.get("telefono", "")).strip()
        if not tel:
            continue
        try:
            fecha = datetime.fromisoformat(str(f.get("fecha", "")).replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if tel not in primeras or fecha < primeras[tel]:
            primeras[tel] = fecha
    n = 0
    for f in clientes:
        if str(f.get("estatus", "")).strip() != "agendado":
            continue
        if not _en_ventana(f, desde, hasta):
            continue
        tel = str(f.get("telefono", "")).strip()
        if tel and tel in primeras and primeras[tel] < desde:
            n += 1
    return n


def delta_citas_semana_anterior(filas_reporte: list[dict], desde: datetime,
                                hasta: datetime, citas_n: int) -> int | None:
    """Diferencia de citas vs la semana anterior, desde la pestaña
    Reporte. None si no hay fila de la semana previa (primera
    semana o pestaña vacía): sin dato no se afirma nada."""
    esperada = f"{(desde - timedelta(days=7)).date()} a {desde.date()}"
    for f in filas_reporte or []:
        if str(f.get("semana", "")).strip() == esperada:
            try:
                prev = int(float(str(f.get("citas_agendadas", "")).strip()))
            except (ValueError, TypeError):
                return None
            return citas_n - prev
    return None


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

    # (v3.20.5) Valor estimado de lo agendado en las últimas 24 h,
    # con los precios de Conocimiento. Sin precio conocido, no sale
    # la línea: el digest nunca inventa pesos.
    _agendadas_24h = [
        c for c in clientes
        if _en_ventana(c, desde, hasta)
        and str(c.get("estatus", "")).strip() == "agendado"
    ]
    try:
        _conoc_24h = leer_pestana("Conocimiento")
    except Exception:
        _conoc_24h = []
    _valor_24h, _con_precio_24h, _ = valor_estimado_citas(
        _agendadas_24h, _conoc_24h)

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
        + (
            f"Valor estimado agendado: ${_valor_24h:,} MXN"
            f" ({_con_precio_24h} citas con precio conocido)\n"
            if _con_precio_24h else ""
        )
        + f"Casos pasados a una persona: {conteo['handoffs']}\n\n"
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


def _html_reporte_semanal(*, nombre_neg: str, semana: str, citas: list[dict],
                          humanos: list[dict], recuperar: list[dict],
                          atendidos: int, resueltas: int, pct: int, citas_n: int,
                          canceladas: int, no_show: int, horas: float,
                          sin_respuesta: int, resumen: str,
                          confirmaciones: int = 0, valor: int = 0,
                          citas_con_precio: int = 0,
                          fuera_horario: int | None = None,
                          volvieron: int = 0,
                          delta: int | None = None) -> str:
    """Versión HTML del reporte semanal (v3.9): misma información que
    el texto, con el diseño limpio que el dueño lee en un minuto.

    Los datos salen de las hojas; lo estimado va marcado como
    estimado. Todo el texto del negocio se escapa antes de meterlo
    al HTML.
    """
    def e(v) -> str:
        return _html.escape(str(v or ""))

    def _filas_citas() -> str:
        if not citas:
            return ('<tr><td style="padding:8px 10px; color:#6B7280;">'
                    'Ninguna esta semana.</td></tr>')
        filas = []
        for i, f in enumerate(citas):
            fondo = ' style="background:#F9FAFB;"' if i % 2 else ""
            filas.append(
                f'<tr{fondo}><td style="padding:8px 10px; border-bottom:1px solid #E5E7EB;">'
                f'{e(f.get("nombre") or f.get("telefono"))} — {e(f.get("motivo") or "cita")}</td>'
                f'<td align="right" style="padding:8px 10px; border-bottom:1px solid #E5E7EB;">'
                f'{e(formatear_cita_bonita(str(f.get("fecha_cita", ""))))}</td></tr>'
            )
        return "".join(filas)

    def _lista_humanos() -> str:
        if not humanos:
            return "Ninguna esta semana."
        return "<br>".join(
            f'• <strong>{e(f.get("nombre") or f.get("telefono"))}</strong>'
            f' — {e(f.get("motivo") or "sin motivo")} ({e(_fecha_corta(str(f.get("fecha", ""))))})'
            for f in humanos
        )

    def _lista_recuperar() -> str:
        if not recuperar:
            return "Nadie por recuperar esta semana."
        return "<br>".join(
            f'<strong>{e(f.get("nombre") or f.get("telefono"))}</strong> preguntó por '
            f'{e(f.get("motivo"))}.<br><span style="color:#6B7280;">Borrador listo para copiar: '
            f'«Hola {e(f.get("nombre") or "")}, vi que preguntaste por {e(f.get("motivo"))}. '
            f'¿Te aparto un lugar esta semana?»</span>'
            for f in recuperar
        )

    # (v3.20.5) Filas de retorno: solo si hay dato que afirmar.
    _filas_retorno = ""
    if citas_con_precio:
        _filas_retorno += (
            '<tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            'Valor estimado de las citas agendadas</td>'
            f'<td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            f'<strong>${valor:,} MXN</strong> ({citas_con_precio} de {len(citas)} con precio conocido)</td></tr>'
        )
    if fuera_horario is not None:
        _filas_retorno += (
            '<tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            'Conversaciones atendidas fuera de tu horario</td>'
            f'<td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            f'<strong>{fuera_horario}</strong></td></tr>'
        )
    _filas_retorno += (
        '<tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
        'Clientes que volvieron y agendaron</td>'
        f'<td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
        f'<strong>{volvieron}</strong></td></tr>'
    )
    if delta is not None:
        _filas_retorno += (
            '<tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            'Citas vs semana pasada</td>'
            f'<td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;">'
            f'<strong>{delta:+d}</strong></td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tu semana en {e(nombre_neg)} — {e(semana)}</title>
</head>
<body style="margin:0; padding:0; background:#F3F5F6; font-family:Arial, Helvetica, sans-serif;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F5F6; padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background:#FFFFFF; border-radius:12px; overflow:hidden; border:1px solid #E5E7EB;">

  <tr><td style="background:#2E5266; padding:24px 28px;">
    <div style="font-size:13px; letter-spacing:2px; color:#9FC5CE; text-transform:uppercase;">Reporte semanal</div>
    <div style="font-size:22px; font-weight:bold; color:#FFFFFF; margin-top:6px;">Tu semana en {e(nombre_neg)}</div>
    <div style="font-size:14px; color:#D7E5EA; margin-top:4px;">{e(semana)} · llega por correo los lunes 08:00</div>
  </td></tr>

  <tr><td style="padding:22px 28px 6px 28px; font-size:15px; color:#374151; line-height:1.55;">
    Aquí está tu semana, <strong>sin que tengas que entrar a ningún lado</strong>. Los números salen de tus conversaciones reales; nada está inventado.
  </td></tr>

  <tr><td style="padding:16px 28px 4px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="33%" align="center" style="padding:8px;">
          <div style="font-size:26px; font-weight:bold; color:#2E5266;">{atendidos}</div>
          <div style="font-size:12px; color:#6B7280;">Conversaciones<br>atendidas</div>
        </td>
        <td width="33%" align="center" style="padding:8px;">
          <div style="font-size:26px; font-weight:bold; color:#2E5266;">{citas_n}</div>
          <div style="font-size:12px; color:#6B7280;">Citas<br>creadas</div>
        </td>
        <td width="33%" align="center" style="padding:8px;">
          <div style="font-size:26px; font-weight:bold; color:#2E5266;">~{horas:.1f} h</div>
          <div style="font-size:12px; color:#6B7280;">Tiempo ahorrado<br>estimado</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:14px 28px 4px 28px;">
    <div style="font-size:16px; font-weight:bold; color:#1F2937; border-left:4px solid #2E5266; padding-left:10px;">📅 CITAS CONFIRMADAS ({len(citas)})</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px; font-size:14px; color:#374151;">
      {_filas_citas()}
    </table>
  </td></tr>

  <tr><td style="padding:22px 28px 4px 28px;">
    <div style="font-size:16px; font-weight:bold; color:#1F2937; border-left:4px solid #D97706; padding-left:10px;">🙋 NECESITARON ATENCIÓN HUMANA ({len(humanos)})</div>
    <div style="font-size:14px; color:#374151; margin-top:10px; line-height:1.6;">
      {_lista_humanos()}
    </div>
  </td></tr>

  <tr><td style="padding:22px 28px 4px 28px;">
    <div style="font-size:16px; font-weight:bold; color:#1F2937; border-left:4px solid #059669; padding-left:10px;">💬 CLIENTES POR RECUPERAR ({len(recuperar)})</div>
    <div style="font-size:14px; color:#374151; margin-top:10px; line-height:1.6;">
      {_lista_recuperar()}
    </div>
  </td></tr>

  <tr><td style="padding:22px 28px 6px 28px;">
    <div style="font-size:16px; font-weight:bold; color:#1F2937; border-left:4px solid #2E5266; padding-left:10px;">📊 TU SEMANA EN NÚMEROS</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px; font-size:14px; color:#374151;">
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Conversaciones atendidas</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{atendidos}</strong></td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Resueltas sin pasar a humano</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{resueltas} ({pct}%)</strong></td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Citas confirmadas</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{citas_n}</strong></td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Canceladas / no-show</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{canceladas} / {no_show}</strong></td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Confirmaciones de asistencia</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{confirmaciones}</strong></td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Mensajes sin respuesta del robot</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>{sin_respuesta}</strong> (todos registrados)</td></tr>
      <tr><td style="padding:7px 0; border-bottom:1px solid #F3F4F6;">Tiempo ahorrado estimado</td><td align="right" style="padding:7px 0; border-bottom:1px solid #F3F4F6;"><strong>~{horas:.1f} h</strong> (5 min por conversación resuelta)</td></tr>
      {_filas_retorno}
    </table>
  </td></tr>

  <tr><td style="padding:20px 28px;">
    <div style="background:#E8F1F2; border-radius:8px; padding:16px 18px; font-size:14px; color:#374151; line-height:1.6;">
      <strong>Resumen de la semana:</strong> {e(resumen)}
    </div>
  </td></tr>

  <tr><td style="background:#2E5266; padding:18px 28px; font-size:13px; color:#D7E5EA; text-align:center; line-height:1.6;">
    Este correo llega automáticamente cada lunes a las 08:00.<br>
    ¿Quieres pausarlo o cambiar el destino? Responde a este correo o avisa a tu contacto.
  </td></tr>

</table>
</td></tr>
</table>

</body>
</html>"""


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

    # (v3.9) Canceladas y no-show desde el espejo de Citas. Solo
    # cuenta lo que el robot registró desde v3.9; si la pestaña no
    # existe o está vacía, da 0 y el correo sale igual.
    try:
        _espejo = leer_pestana("Citas")
    except Exception:
        _espejo = []
    canceladas = sum(
        1 for f in _espejo
        if _en_ventana_texto(str(f.get("Fecha", "")), desde, hasta)
        and str(f.get("Estado", "")).strip() == "Cancelada"
    )
    no_show = sum(
        1 for f in _espejo
        if _en_ventana_texto(str(f.get("Fecha", "")), desde, hasta)
        and str(f.get("Estado", "")).strip() == "No-show"
    )
    # (v3.12, Sereno función 06) Confirmaciones de asistencia: el
    # paciente confirmó por texto que sí vendrá (queda en las Notas
    # del espejo). Sin recordatorios, da 0 y el correo sale igual.
    confirmaciones = sum(
        1 for f in _espejo
        if _en_ventana_texto(str(f.get("Fecha", "")), desde, hasta)
        and "confirmó asistencia" in str(f.get("Notas", "") or "")
    )

    # (v3.20.5, auditoría de negocio) Métricas de retorno para el
    # cliente que paga: valor estimado en pesos de las citas,
    # conversaciones fuera de horario, clientes que volvieron y
    # agendaron, y delta vs la semana anterior. Todo sale de las
    # hojas; lo que no se puede comprobar no se afirma.
    try:
        _conocimiento = leer_pestana("Conocimiento")
    except Exception:
        _conocimiento = []
    valor, citas_con_precio, _citas_sin_precio = valor_estimado_citas(
        citas, _conocimiento)
    fuera_horario = conversaciones_fuera_de_horario(
        conversaciones, _conocimiento, desde, hasta)
    volvieron = clientes_que_volvieron(clientes, conversaciones, desde, hasta)
    try:
        _filas_reporte = leer_pestana("Reporte")
    except Exception:
        _filas_reporte = []
    delta = delta_citas_semana_anterior(
        _filas_reporte, desde, hasta, conteo["citas_agendadas"])

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
    # (v3.20.5) Los números de retorno también van al resumen de la
    # IA, para que el texto mencione el valor y no solo los conteos.
    _lineas_retorno = (
        f"Valor estimado de las citas agendadas: ${valor} MXN "
        f"({citas_con_precio} citas con precio conocido)\n"
        f"Conversaciones fuera de horario: "
        f"{fuera_horario if fuera_horario is not None else 'sin dato'}\n"
        f"Clientes que volvieron y agendaron: {volvieron}\n"
    )
    if delta is not None:
        _lineas_retorno += f"Citas vs semana pasada: {delta:+d}\n"
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
        f"Confirmaciones de asistencia: {confirmaciones}\n"
        f"Casos pasados a una persona: {conteo['handoffs']}\n"
        f"Mensajes sin responder porque una persona atendía: {conteo['sin_respuesta_por_humano']}\n"
        f"{_lineas_retorno}"
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

    # (v3.20.5) Líneas de retorno: solo salen si hay dato que
    # afirmar. Sin precios conocidos en Conocimiento, no se inventa
    # un valor en pesos; sin horario configurado, no se afirma lo
    # de fuera de horario; sin semana previa, no hay delta.
    _lineas_valor = ""
    if citas_con_precio:
        _lineas_valor += (
            f"- Valor estimado de las citas agendadas: ${valor:,} MXN"
            f" (precio conocido en {citas_con_precio} de {len(citas)} citas)\n"
        )
    if fuera_horario is not None:
        _lineas_valor += (
            f"- Conversaciones atendidas fuera de tu horario: {fuera_horario}\n"
        )
    _lineas_valor += f"- Clientes que volvieron y agendaron: {volvieron}\n"
    if delta is not None:
        _lineas_valor += f"- Citas vs semana pasada: {delta:+d}\n"

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
        f"- Canceladas: {canceladas} · No-show: {no_show}\n"
        f"- Confirmaciones de asistencia: {confirmaciones}\n"
        f"- Clientes atendidos: {conteo['clientes_calificados']}\n"
        f"- Tiempo ahorrado estimado: ~{horas:.1f} h"
        " (5 min por conversación resuelta)\n"
        f"- Mensajes sin respuesta del robot: {sin_respuesta}"
        " (todos quedaron registrados en la hoja)\n"
        f"{_lineas_valor}\n"
        f"{resumen}\n"
    )
    html = _html_reporte_semanal(
        nombre_neg=nombre_neg, semana=semana, citas=citas, humanos=humanos,
        recuperar=recuperar, atendidos=atendidos, resueltas=resueltas, pct=pct,
        citas_n=conteo["citas_agendadas"], canceladas=canceladas, no_show=no_show,
        horas=horas, sin_respuesta=sin_respuesta, resumen=resumen,
        confirmaciones=confirmaciones, valor=valor,
        citas_con_precio=citas_con_precio, fuera_horario=fuera_horario,
        volvieron=volvieron, delta=delta,
    )
    enviar_correo(
        correo_dueno(),
        f"Tu semana en {nombre_neg} — citas, humanos y resumen",
        cuerpo,
        html=html,
    )
    guardar_reporte(
        semana,
        conteo["mensajes_atendidos"],
        conteo["clientes_calificados"],
        conteo["citas_agendadas"],
        conteo["handoffs"],
        resumen,
    )
    return {
        "semana": semana, **conteo, "resumen": resumen,
        "valor_estimado": valor, "citas_con_precio": citas_con_precio,
        "fuera_de_horario": fuera_horario, "volvieron": volvieron,
        "delta_citas": delta,
    }
