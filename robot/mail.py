"""Aloara: correos al dueño. Solo dos tipos de correo salen de aquí:
1. Alertas (handoff, urgencia, oportunidad, cita, interrupción):
   el dueño se entera al momento, con la voz y el diseño Aloara.
2. Reporte semanal: qué hizo el robot esa semana (vive en report.py).

Identidad Aloara: "Siempre presente." Voz serena y resolutiva, sin
jerga técnica ("Es momento de conectar", nunca "Handoff activado").
Diseño: Forest #123D36, Intelligence #36B89C, Mineral #F1F5F3,
Carbon #141B19, tipografía Manrope (con Arial de respaldo en correo).

Se usa SMTP con una contraseña de aplicación (no tu clave real).
Por defecto es Gmail (smtp.gmail.com:587); si el dueño solo tiene
otro correo (p. ej. iCloud de Apple: smtp.mail.me.com:587), basta
poner SMTP_HOST, SMTP_USER y SMTP_PASSWORD en Render (v3.22.0).
La contraseña va en el .env como SMTP_PASSWORD (o
GMAIL_APP_PASSWORD en Gmail) y nunca se escribe en el código.

Si no hay usuario o contraseña de correo, mandar correo falla con
un mensaje claro en vez de romperse en silencio: el robot sigue
atendiendo, pero el dueño no recibe la alerta (y eso queda en el
registro).

Versión 2.1: esa falla de correo ya no puede romper una respuesta de
WhatsApp. Quien llama a alerta_handoff / alerta_error lo hace con
best-effort (ver logic._avisar_por_correo y app.DependenciasReales):
el correo se intenta, si falla queda en el registro, y el cliente
recibe igual su respuesta. El reporte semanal sí necesita Gmail para
salir; sin él, ese lunes simplemente no llega el correo.

(v3.21.0, Aloara) Las alertas llevan botón "Continuar conversación"
(wa.me) para abrir el chat de WhatsApp en un toque, y versión HTML
con la identidad Aloara además del texto plano.
"""

from __future__ import annotations

import html as _html
import re
import smtplib
from email.message import EmailMessage

from .config import correo_saliente, settings
from .negocio import correo_dueno


class CorreoError(RuntimeError):
    """No se pudo mandar el correo (falta la contraseña de app, red, etc.)."""


# --- Identidad Aloara -------------------------------------------------------

_FUENTE = "'Manrope', Arial, Helvetica, sans-serif"
_FOREST = "#123D36"
_INTELLIGENCE = "#36B89C"
_MINERAL = "#F1F5F3"
_CARBON = "#141B19"
_GRIS = "#64746C"


def _link_whatsapp(telefono: str) -> str:
    """Enlace wa.me con solo dígitos (sin +, sin espacios)."""
    digitos = re.sub(r"\D", "", str(telefono or ""))
    return f"https://wa.me/{digitos}" if digitos else ""


def _filas_html(filas: list[tuple[str, str]]) -> str:
    """Filas etiqueta/valor con la jerarquía Aloara (etiqueta gris, valor fuerte)."""
    partes = []
    for etiqueta, valor in filas:
        if not valor:
            continue
        partes.append(
            f'<div style="padding:10px 0;border-bottom:1px solid #E3EAE7;">'
            f'<div style="font-size:11px;letter-spacing:1.8px;text-transform:uppercase;'
            f'color:{_GRIS};font-weight:bold;">{_html.escape(etiqueta)}</div>'
            f'<div style="font-size:15px;line-height:1.6;color:{_CARBON};margin-top:3px;">'
            f'{_html.escape(valor)}</div></div>'
        )
    return "".join(partes)


def _bloque_texto_html(titulo: str, texto: str) -> str:
    """Bloque de texto largo (resumen, hilo) en tarjeta suave."""
    if not texto:
        return ""
    return (
        f'<div style="margin-top:18px;">'
        f'<div style="font-size:11px;letter-spacing:1.8px;text-transform:uppercase;'
        f'color:{_GRIS};font-weight:bold;">{_html.escape(titulo)}</div>'
        f'<div style="font-size:14px;line-height:1.7;color:#33413C;background:{_MINERAL};'
        f'border-radius:10px;padding:12px 16px;margin-top:6px;white-space:pre-wrap;">'
        f'{_html.escape(texto)}</div></div>'
    )


def _html_alerta(kicker: str, titulo: str, intro: str, filas: list[tuple[str, str]],
                 boton_texto: str = "", boton_url: str = "",
                 bloques: list[tuple[str, str]] | None = None) -> str:
    """Versión HTML de una alerta, con la identidad Aloara."""
    boton_html = ""
    if boton_texto and boton_url:
        boton_html = (
            f'<div style="margin-top:26px;text-align:center;">'
            f'<a href="{_html.escape(boton_url)}" style="display:inline-block;'
            f'background:{_INTELLIGENCE};color:#FFFFFF;font-size:15px;font-weight:bold;'
            f'text-decoration:none;padding:13px 28px;border-radius:999px;">'
            f'{_html.escape(boton_texto)}</a></div>'
        )
    bloques_html = "".join(
        _bloque_texto_html(t, x) for t, x in (bloques or []) if x
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(titulo)}</title>
</head>
<body style="margin:0;padding:0;background:{_MINERAL};font-family:{_FUENTE};color:{_CARBON};">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_MINERAL};padding:40px 16px;">
<tr><td align="center">

<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#FFFFFF;border-radius:16px;">

  <tr><td style="padding:28px 36px 0 36px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-size:18px;font-weight:bold;color:{_FOREST};">aloara.</td>
        <td align="right" style="font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:{_INTELLIGENCE};font-weight:bold;">{_html.escape(kicker)}</td>
      </tr>
    </table>
    <div style="border-top:1px solid #E3EAE7;margin-top:18px;"></div>
  </td></tr>

  <tr><td style="padding:30px 36px 0 36px;">
    <div style="font-size:24px;line-height:1.3;font-weight:bold;color:{_FOREST};">{_html.escape(titulo)}</div>
    <div style="font-size:15px;line-height:1.7;color:#33413C;margin-top:10px;">{_html.escape(intro)}</div>
  </td></tr>

  <tr><td style="padding:22px 36px 0 36px;">
    {_filas_html(filas)}
    {bloques_html}
    {boton_html}
  </td></tr>

  <tr><td style="padding:32px 36px 30px 36px;">
    <div style="border-top:1px solid #E3EAE7;padding-top:18px;">
      <div style="font-size:13px;color:{_GRIS};">Aloara · Siempre presente.</div>
    </div>
  </td></tr>

</table>

</td></tr>
</table>

</body>
</html>"""


# --- Envío ------------------------------------------------------------------

def enviar_correo(destinatario: str, asunto: str, cuerpo: str,
                  html: str | None = None) -> None:
    """Manda un correo. Si llega `html`, va como multipart: texto plano
    siempre (para clientes sin HTML) y la versión bonita encima."""
    host, puerto, usuario, contrasena = correo_saliente()
    if not usuario or not contrasena:
        raise CorreoError(
            "Falta el correo saliente en el .env (SMTP_USER/SMTP_PASSWORD "
            "o GMAIL_USER/GMAIL_APP_PASSWORD). Crea una contraseña de "
            "aplicación en tu proveedor (ver README, paso 4)."
        )
    mensaje = EmailMessage()
    mensaje["From"] = usuario
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    if html:
        mensaje.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, puerto, timeout=30) as servidor:
            servidor.starttls()
            servidor.login(usuario, contrasena)
            servidor.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as exc:
        raise CorreoError(f"No se pudo mandar el correo a {destinatario}: {exc}") from exc


def alerta_error(motivo: str, telefono: str, ultimo_mensaje: str, fecha: str) -> None:
    """Aloara: detectamos una interrupción. Algo falló (Gemini, Sheets,
    Calendar) y el cliente recibió un "dame un momento". Para que no
    se pierda el caso."""
    cuerpo = (
        "Detectamos una interrupción.\n\n"
        "Hemos perdido la conexión temporalmente al atender a este "
        "cliente; recibió un mensaje de espera. Revísalo cuando puedas.\n\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Fecha: {fecha}\n\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n\n"
        "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Interrupción",
        "Detectamos una interrupción.",
        "Hemos perdido la conexión temporalmente al atender a este cliente; "
        "recibió un mensaje de espera. Revísalo cuando puedas.",
        [("Teléfono", telefono), ("Motivo", motivo), ("Fecha", fecha)],
        bloques=[("Último mensaje del cliente", ultimo_mensaje)],
    )
    enviar_correo(
        correo_dueno(),
        f"Detectamos una interrupción · {telefono}",
        cuerpo,
        html=html,
    )


def alerta_cita_confirmada(
    nombre: str, telefono: str, motivo: str, fecha_bonita: str, fecha: str
) -> None:
    """Aloara Opportunities: se confirmó una cita. El dueño no ve las
    citas en su calendario (el robot agenda en el suyo propio), así
    que sin este correo se entera hasta el lunes."""
    cuerpo = (
        "Tienes una nueva cita.\n\n"
        "Un nuevo espacio en tu agenda.\n\n"
        f"Cliente: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Cita: {fecha_bonita}\n"
        f"Fecha: {fecha}\n\n"
        "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Nueva cita",
        "Tienes una nueva cita.",
        "Un nuevo espacio en tu agenda.",
        [("Cliente", nombre or telefono), ("Teléfono", telefono),
         ("Motivo", motivo), ("Cita", fecha_bonita), ("Fecha", fecha)],
    )
    enviar_correo(
        correo_dueno(),
        f"Tienes una nueva cita · {nombre or telefono} — {fecha_bonita}",
        cuerpo,
        html=html,
    )


def alerta_cita_urgente(
    nombre: str, telefono: str, motivo: str, fecha_bonita: str, fecha: str,
    razon: str = "",
) -> None:
    """Aloara Priority: se confirmó una cita marcada como urgente.

    El porqué va en el correo: el dueño sabe qué atender primero sin
    buscar en la hoja. Esta alerta siempre sale en el momento (no
    espera al correo semanal): una urgencia no puede esperar al lunes.
    """
    wa = _link_whatsapp(telefono)
    cuerpo = (
        "Prioridad alta.\n\n"
        "Tu equipo necesita intervenir.\n\n"
        "Hemos detectado una conversación que requiere atención "
        "prioritaria.\n\n"
        f"Cliente: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Cita: {fecha_bonita}\n"
        f"Fecha: {fecha}\n\n"
        f"Por qué es urgente:\n{razon or motivo}\n\n"
        + (f"Atender ahora: {wa}\n\n" if wa else "")
        + "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Prioridad alta",
        "Tu equipo necesita intervenir.",
        "Hemos detectado una conversación que requiere atención prioritaria.",
        [("Cliente", nombre or telefono), ("Teléfono", telefono),
         ("Motivo", motivo), ("Cita", fecha_bonita), ("Fecha", fecha)],
        boton_texto="Atender ahora" if wa else "",
        boton_url=wa,
        bloques=[("Por qué es urgente", razon or motivo)],
    )
    enviar_correo(
        correo_dueno(),
        f"Atención prioritaria requerida · {nombre or telefono} — {fecha_bonita}",
        cuerpo,
        html=html,
    )


def alerta_lead_caliente(
    nombre: str, telefono: str, motivo: str, ultimo_mensaje: str, fecha: str
) -> None:
    """Aloara Opportunities: este cliente pidió agendar YA (no solo
    preguntó un precio). Es el momento de estar atento: si el robot le
    ofrece una hora y el cliente confirma, llega además la de cita
    confirmada."""
    wa = _link_whatsapp(telefono)
    cuerpo = (
        "Tienes una nueva oportunidad.\n\n"
        "Un prospecto ha mostrado interés y está listo para recibir "
        "seguimiento.\n\n"
        f"Nuevo prospecto: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Interés: {motivo}\n"
        f"Fecha: {fecha}\n\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n\n"
        + (f"Ver oportunidad: {wa}\n\n" if wa else "")
        + "Las buenas conversaciones abren nuevas posibilidades.\n\n"
        "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Nueva oportunidad",
        "Tienes una nueva oportunidad.",
        "Un prospecto ha mostrado interés y está listo para recibir seguimiento.",
        [("Nuevo prospecto", nombre or telefono), ("Teléfono", telefono),
         ("Interés", motivo), ("Fecha", fecha)],
        boton_texto="Ver oportunidad" if wa else "",
        boton_url=wa,
        bloques=[("Último mensaje del cliente", ultimo_mensaje)],
    )
    enviar_correo(
        correo_dueno(),
        f"Una nueva oportunidad llegó a tu negocio · {nombre or telefono}",
        cuerpo,
        html=html,
    )


def alerta_cita_pendiente(
    nombre: str, telefono: str, motivo: str, fecha_bonita: str, fecha: str
) -> None:
    """Aloara: la cita NO quedó creada (falló el calendario).

    Decisión 1: nunca inventar una cita. Al cliente se le dijo que su
    solicitud quedó pendiente; el dueño la crea a mano o llama.
    """
    cuerpo = (
        "Una cita quedó pendiente de crear.\n\n"
        "El cliente pidió una cita por WhatsApp, pero el calendario "
        "falló al crearla. Al cliente se le dijo que su solicitud "
        "quedó pendiente y que el equipo le escribe en breve.\n\n"
        f"Cliente: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Fecha pedida: {fecha_bonita}\n"
        f"Alerta: {fecha}\n\n"
        "Crea la cita a mano en el calendario o llama al cliente.\n\n"
        "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Cita pendiente",
        "Una cita quedó pendiente de crear.",
        "El cliente pidió una cita por WhatsApp, pero el calendario falló "
        "al crearla. Al cliente se le dijo que su solicitud quedó pendiente "
        "y que el equipo le escribe en breve.",
        [("Cliente", nombre or telefono), ("Teléfono", telefono),
         ("Motivo", motivo), ("Fecha pedida", fecha_bonita), ("Alerta", fecha)],
        bloques=[("Qué hacer", "Crea la cita a mano en el calendario o llama al cliente.")],
    )
    enviar_correo(
        correo_dueno(),
        f"Una cita quedó pendiente de crear · {nombre or telefono} — {fecha_bonita}",
        cuerpo,
        html=html,
    )


def alerta_handoff(
    nombre: str, telefono: str, motivo: str, ultimo_mensaje: str, fecha: str,
    resumen: str = "", hilo: str = "",
) -> None:
    """Aloara Connect: este cliente necesita una persona. El robot se calla.

    `resumen` es la memoria de la conversación (Clientes): el dueño
    recibe el contexto junto con la alerta, sin tener que buscar en
    la hoja ("entrega el contexto"). `hilo` trae los últimos mensajes
    de la conversación, para que recepción vea la foto completa sin
    abrir la hoja. El botón "Continuar conversación" abre el chat de
    WhatsApp en un toque (wa.me).
    """
    wa = _link_whatsapp(telefono)
    _resumen_txt = (
        f"\nResumen de la conversación:\n{resumen}\n" if resumen else ""
    )
    _hilo_txt = (
        f"\nÚltimos mensajes de la conversación:\n{hilo}\n" if hilo else ""
    )
    cuerpo = (
        "Es momento de conectar.\n\n"
        "Un cliente necesita asistencia personalizada. Tu equipo puede "
        "continuar mejor esta conversación.\n\n"
        f"Contacto: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Canal: WhatsApp\n"
        f"Motivo: {motivo}\n"
        f"Hora: {fecha}\n"
        f"{_resumen_txt}"
        f"{_hilo_txt}\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n\n"
        + (f"Continuar conversación: {wa}\n\n" if wa else "")
        + "El contexto de la conversación está disponible para tu equipo. "
        "El robot queda en pausa 2 horas desde que tú le escribas a este "
        "cliente.\n\n"
        "Aloara · Siempre presente.\n"
    )
    html = _html_alerta(
        "Requiere atención",
        "Es momento de conectar.",
        "Un cliente necesita asistencia personalizada. Tu equipo puede "
        "continuar mejor esta conversación.",
        [("Contacto", nombre or telefono), ("Teléfono", telefono),
         ("Canal", "WhatsApp"), ("Motivo", motivo), ("Hora", fecha)],
        boton_texto="Continuar conversación" if wa else "",
        boton_url=wa,
        bloques=[
            ("Resumen de la conversación", resumen),
            ("Últimos mensajes de la conversación", hilo),
            ("Último mensaje del cliente", ultimo_mensaje),
        ],
    )
    enviar_correo(
        correo_dueno(),
        f"Una conversación necesita tu atención · {nombre or telefono}",
        cuerpo,
        html=html,
    )
