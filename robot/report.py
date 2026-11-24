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
    """Versión HTML del reporte semanal (v3.20.8): diseño v3 aprobado
    por Jose — el número ES el titular, jerarquía por tipografía y
    espacios, sin cajas densas. Misma información que el texto.

    Los datos salen de las hojas; lo estimado va marcado como
    estimado. Todo el texto del negocio se escapa antes de meterlo
    al HTML.
    """
    def e(v) -> str:
        return _html.escape(str(v or ""))

    # --- El número: titular. Sin precio conocido no se inventa $. ---
    if citas_con_precio:
        _numero_grande = (
            f"${valor:,}"
            ' <span style="font-size:22px; font-weight:normal; '
            'color:#8A99A3;">MXN</span>'
        )
    else:
        _numero_grande = f"{citas_n}"
    _plural_citas = "s" if citas_n != 1 else ""
    _linea_perdida = ""
    if fuera_horario:
        _linea_perdida = (
            '<div style="font-size:15px; line-height:1.65; color:#44565F; '
            f'margin-top:8px;">{fuera_horario} llegaron fuera de tu horario. '
            'Sin el robot, eran clientes perdidos.</div>'
        )

    def _filas_citas() -> str:
        if not citas:
            return ('<div style="font-size:15px; color:#8A99A3; '
                    'margin-top:14px;">Ninguna esta semana.</div>')
        filas = []
        for i, f in enumerate(citas):
            estilo = "padding:12px 0; font-size:15px;"
            if i < len(citas) - 1:
                estilo += " border-bottom:1px solid #F0F3F5;"
            filas.append(
                f'<div style="{estilo}">'
                f'{e(f.get("nombre") or f.get("telefono"))}'
                f' <span style="color:#8A99A3;">· '
                f'{e(f.get("motivo") or "cita")}</span>'
                f'<span style="float:right; color:#8A99A3;">'
                f'{e(formatear_cita_bonita(str(f.get("fecha_cita", ""))))}'
                '</span></div>'
            )
        return "".join(filas)

    def _bloque_humanos() -> str:
        if not humanos:
            return ""
        items = []
        for f in humanos:
            items.append(
                '<div style="font-size:15px; line-height:1.65; margin-top:14px;">'
                f'<strong>{e(f.get("nombre") or f.get("telefono"))}</strong> '
                f'<span style="color:#8A99A3;">— '
                f'{e(f.get("motivo") or "sin motivo")}'
                f' ({e(_fecha_corta(str(f.get("fecha", ""))))})</span></div>'
            )
        return "".join(items)

    def _bloque_recuperar() -> str:
        if not recuperar:
            return ""
        partes = []
        for f in recuperar:
            nombre = e(f.get("nombre") or f.get("telefono"))
            motivo = e(f.get("motivo") or "")
            partes.append(
                '<div style="font-size:15px; line-height:1.65; margin-top:18px;">'
                f'<strong>{nombre}</strong> '
                f'<span style="color:#8A99A3;">preguntó por {motivo} '
                'y no agendó.</span></div>'
                '<div style="font-size:14px; line-height:1.65; color:#33424D; '
                'background:#F4F8FA; border-radius:10px; padding:12px 16px; '
                'margin-top:8px;">'
                f'«Hola {e(f.get("nombre") or "")}, vi que preguntaste por '
                f'{motivo}. ¿Te aparto un lugar esta semana?»</div>'
            )
        return "".join(partes)

    if humanos or recuperar:
        _bloque_atencion = _bloque_humanos() + _bloque_recuperar()
    else:
        _bloque_atencion = (
            '<div style="font-size:15px; color:#8A99A3; margin-top:14px;">'
            'Nada pendiente esta semana.</div>'
        )

    # --- En números: lista compacta con líneas, sin tabla densa. ---
    _filas_numeros = [
        ("Conversaciones atendidas", str(atendidos)),
        ("Resueltas sin pasar a humano", f"{resueltas} ({pct}%)"),
        ("Citas confirmadas", str(citas_n)),
        ("Canceladas / no-show", f"{canceladas} / {no_show}"),
        ("Confirmaciones de asistencia", str(confirmaciones)),
        ("Tiempo ahorrado estimado", f"~{horas:.1f} h"),
        ("Mensajes sin respuesta del robot",
         f"{sin_respuesta} (todos registrados)"),
        ("Clientes que volvieron y agendaron", str(volvieron)),
    ]
    if citas_con_precio:
        _filas_numeros.append(
            ("Valor estimado de las citas agendadas",
             f"${valor:,} MXN ({citas_con_precio} de {len(citas)} "
             "con precio conocido)")
        )
    if fuera_horario is not None:
        _filas_numeros.append(
            ("Conversaciones atendidas fuera de tu horario",
             str(fuera_horario))
        )
    if delta is not None:
        _filas_numeros.append(
            ("Citas vs semana pasada", f"{delta:+d}")
        )
    _filas_numeros_html = "".join(
        f'<div style="padding:10px 0; font-size:15px;'
        f'{" border-bottom:1px solid #F0F3F5;" if i < len(_filas_numeros) - 1 else ""}">'
        f'{e(etiqueta)}<span style="float:right; font-weight:bold; '
        f'color:#2E5266;">{e(dato)}</span></div>'
        for i, (etiqueta, dato) in enumerate(_filas_numeros)
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tu semana en {e(nombre_neg)} — {e(semana)}</title>
</head>
<body style="margin:0; padding:0; background:#F7F9FA; font-family:Arial, Helvetica, sans-serif; color:#1F2A33;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F7F9FA; padding:40px 16px;">
<tr><td align="center">

<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background:#FFFFFF; border-radius:16px;">

  <tr><td style="padding:28px 36px 0 36px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-size:15px; font-weight:bold; color:#2E5266;">{e(nombre_neg)}</td>
        <td align="right" style="font-size:13px; color:#8A99A3;">{e(semana)}</td>
      </tr>
    </table>
    <div style="border-top:1px solid #E7ECEE; margin-top:20px;"></div>
  </td></tr>

  <tr><td style="padding:36px 36px 0 36px;">
    <div style="font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:#8A99A3; font-weight:bold;">Esta semana tu robot agendó</div>
    <div style="font-size:60px; line-height:1; font-weight:bold; color:#2E5266; margin-top:10px;">{_numero_grande}</div>
    <div style="font-size:15px; line-height:1.65; color:#44565F; margin-top:14px;">{citas_n} cita{_plural_citas} confirmada{_plural_citas}. {atendidos} conversaciones atendidas, {resueltas} resueltas sin pasar a humano.</div>
    {_linea_perdida}
  </td></tr>

  <tr><td style="padding:40px 36px 0 36px;">
    <div style="font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:#2E5266; font-weight:bold;">CITAS CONFIRMADAS</div>
    {_filas_citas()}
  </td></tr>

  <tr><td style="padding:40px 36px 0 36px;">
    <div style="font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:#2E5266; font-weight:bold;">NECESITA TU ATENCIÓN</div>
    {_bloque_atencion}
  </td></tr>

  <tr><td style="padding:40px 36px 0 36px;">
    <div style="font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:#2E5266; font-weight:bold;">TU SEMANA EN UNA LÍNEA</div>
    <div style="font-size:15px; line-height:1.75; color:#33424D; margin-top:12px;">{e(resumen)}</div>
  </td></tr>

  <tr><td style="padding:40px 36px 0 36px;">
    <div style="font-size:12px; letter-spacing:2.5px; text-transform:uppercase; color:#2E5266; font-weight:bold;">TU SEMANA EN NÚMEROS</div>
    <div style="margin-top:6px;">{_filas_numeros_html}</div>
  </td></tr>

  <tr><td style="padding:40px 36px 32px 36px;">
    <div style="border-top:1px solid #E7ECEE; padding-top:20px;">
      <div style="font-size:13px; color:#8A99A3;">Sereno · tu recepcionista digital, trabajando 24/7.</div>
      <div style="font-size:12px; color:#B4C0C7; margin-top:4px;">Valores estimados con base en tus precios.</div>
    </div>
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

    # (v3.20.8) Cuerpo de texto con la misma jerarquía que el HTML
    # v3: el número primero, luego citas, atención y resumen.
    # Las líneas de retorno solo salen si hay dato que afirmar.
    citas_n = conteo["citas_agendadas"]
    _titular_valor = (
        f" por un valor estimado de ${valor:,} MXN"
        if citas_con_precio else ""
    )
    _plural = "s" if citas_n != 1 else ""
    _linea_fuera = ""
    if fuera_horario:
        _linea_fuera = (
            f"{fuera_horario} llegaron fuera de tu horario. "
            "Sin el robot, eran clientes perdidos.\n"
        )
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
        f"Esta semana tu robot agendó {citas_n} cita{_plural}{_titular_valor}.\n"
        f"{atendidos} conversaciones atendidas, {resueltas} ({pct}%) "
        "resueltas sin pasar a humano.\n"
        f"{_linea_fuera}\n"
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
