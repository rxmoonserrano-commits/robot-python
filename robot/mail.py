"""Gmail: mandar correos al dueño. Solo dos tipos de correo salen de aquí:
1. Alerta de handoff: un cliente necesita una persona.
2. Reporte semanal: qué hizo el robot esa semana.

Se usa SMTP de Gmail con una contraseña de aplicación (no tu clave de
Google). Se crea en tu cuenta de Google: Seguridad → Verificación en
2 pasos → Contraseñas de aplicaciones → Correo. Esa contraseña va en
el .env como GMAIL_APP_PASSWORD y nunca se escribe en el código.

Si GMAIL_USER o GMAIL_APP_PASSWORD faltan, mandar correo falla con un
mensaje claro en vez de romperse en silencio: el robot sigue atendiendo,
pero el dueño no recibe la alerta (y eso queda en el registro).

Versión 2.1: esa falla de correo ya no puede romper una respuesta de
WhatsApp. Quien llama a alerta_handoff / alerta_error lo hace con
best-effort (ver logic._avisar_por_correo y app.DependenciasReales):
el correo se intenta, si falla queda en el registro, y el cliente
recibe igual su respuesta. El reporte semanal sí necesita Gmail para
salir; sin él, ese lunes simplemente no llega el correo.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import settings


class CorreoError(RuntimeError):
    """No se pudo mandar el correo (falta la contraseña de app, red, etc.)."""


def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Manda un correo de texto plano. Simple, sin adornos."""
    if not settings.gmail_user or not settings.gmail_app_password:
        raise CorreoError(
            "Falta GMAIL_USER o GMAIL_APP_PASSWORD en el .env. "
            "Crea una contraseña de aplicación en tu cuenta de Google (ver README, paso 4)."
        )
    mensaje = EmailMessage()
    mensaje["From"] = settings.gmail_user
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as servidor:
            servidor.starttls()
            servidor.login(settings.gmail_user, settings.gmail_app_password)
            servidor.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as exc:
        raise CorreoError(f"No se pudo mandar el correo a {destinatario}: {exc}") from exc


def alerta_error(motivo: str, telefono: str, ultimo_mensaje: str, fecha: str) -> None:
    """Correo al dueño: algo falló (Gemini, Sheets, Calendar) y el cliente
    recibió un "dame un momento". Para que no se pierda el caso."""
    enviar_correo(
        settings.owner_email,
        f"Robot: falló algo con {telefono}",
        "El robot no pudo atender bien a este cliente y le dijo que "
        "esperara un momento. Revísalo tú.\n\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Fecha: {fecha}\n\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n",
    )


def alerta_cita_confirmada(
    nombre: str, telefono: str, motivo: str, fecha_bonita: str, fecha: str
) -> None:
    """Correo al dueño: se confirmó una cita. El dueño no ve las citas
    en su calendario (el robot agenda en el suyo propio), así que sin
    este correo se entera hasta el lunes."""
    enviar_correo(
        settings.owner_email,
        f"¡Nueva cita! {nombre or telefono} — {fecha_bonita}",
        "Se confirmó una cita por WhatsApp.\n\n"
        f"Nombre: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Cita: {fecha_bonita}\n"
        f"Fecha: {fecha}\n",
    )


def alerta_lead_caliente(
    nombre: str, telefono: str, motivo: str, ultimo_mensaje: str, fecha: str
) -> None:
    """Correo al dueño: este cliente pidió agendar YA (no solo preguntó
    un precio). Es el momento de estar atento: si el robot le ofrece
    una hora y el cliente confirma, llega además la de cita confirmada."""
    enviar_correo(
        settings.owner_email,
        f"Lead caliente: {nombre or telefono} ({telefono}) quiere agendar",
        "Este cliente pidió una cita en este momento.\n\n"
        f"Nombre: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo: {motivo}\n"
        f"Fecha: {fecha}\n\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n",
    )


def alerta_handoff(
    nombre: str, telefono: str, motivo: str, ultimo_mensaje: str, fecha: str
) -> None:
    """Correo al dueño: este cliente necesita una persona. El robot se calla."""
    enviar_correo(
        settings.owner_email,
        f"Handoff: {nombre or telefono} ({telefono}) necesita una persona",
        "Te paso este cliente para que lo atiendas tú.\n\n"
        f"Nombre: {nombre}\n"
        f"Teléfono: {telefono}\n"
        f"Motivo del handoff: {motivo}\n"
        f"Fecha: {fecha}\n\n"
        "Último mensaje del cliente:\n"
        f"{ultimo_mensaje}\n\n"
        "Resumen: revisa la hoja Conversaciones. Recuerda: el robot queda "
        "en pausa 2 horas desde que tú le escribas a este cliente.",
    )
