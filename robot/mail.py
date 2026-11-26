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


def _alerta_privada(*, nombre: str, telefono: str, categoria: str,
                    asunto: str, titulo: str, intro: str,
                    boton: str = "Continuar conversación") -> None:
    """Envía solo identidad, categoría y enlace; nunca texto libre del chat.

    Las categorías son constantes del programa, no motivos redactados por
    el cliente o por la IA, pues podrían contener datos de salud.
    """
    wa = _link_whatsapp(telefono)
    nombre = str(nombre or "").replace("\n", " ").replace("\r", " ").strip()
    telefono = re.sub(r"\D", "", str(telefono or ""))
    identidad = nombre or telefono
    cuerpo = (f"{titulo}\n\n{intro}\n\n"
              + (f"Contacto: {nombre}\n" if nombre else "")
              + (f"Teléfono: {telefono}\n" if telefono else "")
              + f"Motivo: {categoria}\n"
              + (f"\n{boton}: {wa}\n" if wa else "")
              + "\nAloara · Siempre presente.\n")
    html = _html_alerta(
        categoria, titulo, intro,
        [("Contacto", nombre), ("Teléfono", telefono), ("Motivo", categoria)],
        boton_texto=boton if wa else "", boton_url=wa,
    )
    enviar_correo(correo_dueno(), f"{asunto} · {identidad}" if identidad else asunto,
                   cuerpo, html=html)


def alerta_error(motivo: str, telefono: str, ultimo_mensaje: str, fecha: str) -> None:
    _alerta_privada(nombre="", telefono=telefono, categoria="Interrupción técnica",
                    asunto="Detectamos una interrupción", titulo="Detectamos una interrupción.",
                    intro="El equipo puede revisar la atención en WhatsApp.")


def alerta_cita_confirmada(nombre: str, telefono: str, motivo: str,
                          fecha_bonita: str, fecha: str) -> None:
    _alerta_privada(nombre=nombre, telefono=telefono, categoria="Cita confirmada",
                    asunto="Tienes una nueva cita", titulo="Tienes una nueva cita.",
                    intro="Un nuevo espacio en tu agenda.")


def alerta_cita_urgente(nombre: str, telefono: str, motivo: str,
                       fecha_bonita: str, fecha: str, razon: str = "") -> None:
    _alerta_privada(nombre=nombre, telefono=telefono, categoria="Atención prioritaria",
                    asunto="Atención prioritaria requerida", titulo="Tu equipo necesita intervenir.",
                    intro="Una conversación requiere atención prioritaria.", boton="Atender ahora")


def alerta_lead_caliente(nombre: str, telefono: str, motivo: str,
                         ultimo_mensaje: str, fecha: str) -> None:
    _alerta_privada(nombre=nombre, telefono=telefono, categoria="Nueva oportunidad",
                    asunto="Una nueva oportunidad llegó a tu negocio",
                    titulo="Tienes una nueva oportunidad.",
                    intro="Una persona mostró interés en recibir seguimiento.",
                    boton="Ver oportunidad")


def alerta_cita_pendiente(nombre: str, telefono: str, motivo: str,
                          fecha_bonita: str, fecha: str) -> None:
    _alerta_privada(nombre=nombre, telefono=telefono, categoria="Cita pendiente",
                    asunto="Una cita quedó pendiente de crear",
                    titulo="Una cita quedó pendiente de crear.",
                    intro="Revisa la solicitud y el calendario antes de confirmarla.")


def alerta_handoff(nombre: str, telefono: str, motivo: str, ultimo_mensaje: str,
                   fecha: str, resumen: str = "", hilo: str = "") -> None:
    _alerta_privada(nombre=nombre, telefono=telefono, categoria="Atención humana",
                    asunto="Una conversación necesita tu atención",
                    titulo="Es momento de conectar.",
                    intro="Un cliente necesita asistencia personalizada.")
