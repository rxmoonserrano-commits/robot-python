"""Google Calendar: agendar la cita automáticamente.

Reglas:
- Solo se agenda cuando ya hay nombre, motivo y fecha (lo decide el agente).
- Antes de crear, se revisa que esa hora esté libre. Si está ocupada,
  no se agenda nada: el robot ofrece la siguiente disponible.
- La cita dura DURACION_CITA_MINUTOS (60 por defecto). En la versión de
  n8n había un error: ponía inicio = fin, o sea, una cita de 0 minutos.
  Aquí el fin es inicio + duración, siempre.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import settings
from .sheets import SCOPES


def _servicio_calendar():
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_credentials_json, scopes=SCOPES
        )
    except (FileNotFoundError, ValueError, GoogleAuthError) as exc:
        raise RuntimeError(
            "No encontré las credenciales de Google. Revisa GOOGLE_CREDENTIALS_JSON "
            f"en tu .env (ahora apunta a: {settings.google_credentials_json})."
        ) from exc
    return build("calendar", "v3", credentials=creds)


def _a_datetime(fecha_iso: str) -> datetime:
    """Acepta '2026-11-14T10:00:00' y lo convierte a fecha con zona horaria."""
    texto = fecha_iso.strip().replace("Z", "+00:00")
    fecha = datetime.fromisoformat(texto)
    if fecha.tzinfo is None:
        from zoneinfo import ZoneInfo

        fecha = fecha.replace(tzinfo=ZoneInfo(settings.timezone))
    return fecha


def hora_libre(inicio_iso: str, duracion_min: int | None = None) -> bool:
    """¿Está libre esa hora en el calendario? True = sí, se puede agendar."""
    duracion = duracion_min or settings.duracion_cita_minutos
    inicio = _a_datetime(inicio_iso)
    fin = inicio + timedelta(minutes=duracion)
    servicio = _servicio_calendar()
    ocupados = (
        servicio.freebusy()
        .query(
            body={
                "timeMin": inicio.isoformat(),
                "timeMax": fin.isoformat(),
                "timeZone": settings.timezone,
                "items": [{"id": settings.calendar_id}],
            }
        )
        .execute()
    )
    lista = ocupados.get("calendars", {}).get(settings.calendar_id, {}).get("busy", [])
    return len(lista) == 0


def cancelar_cita(telefono: str, fecha_cita_iso: str) -> bool:
    """Borra del calendario la cita de ese teléfono en esa fecha.

    Busca en el día de la cita el evento cuyo título trae el teléfono
    (los eventos se crean como "Cita <nombre> — <teléfono>") y lo
    borra. Devuelve True si borró al menos uno. Si no encuentra nada,
    no hace nada y devuelve False (no se inventa una cancelación).
    """
    inicio = _a_datetime(fecha_cita_iso)
    dia_inicio = inicio.replace(hour=0, minute=0, second=0, microsecond=0)
    dia_fin = dia_inicio + timedelta(days=1)
    servicio = _servicio_calendar()
    eventos = (
        servicio.events()
        .list(
            calendarId=settings.calendar_id,
            timeMin=dia_inicio.isoformat(),
            timeMax=dia_fin.isoformat(),
            singleEvents=True,
        )
        .execute()
        .get("items", [])
    )
    borrados = 0
    for evento in eventos:
        if str(telefono) in str(evento.get("summary", "")):
            servicio.events().delete(
                calendarId=settings.calendar_id, eventId=evento["id"]
            ).execute()
            borrados += 1
    return borrados > 0


def crear_cita(
    nombre: str,
    telefono: str,
    motivo: str,
    inicio_iso: str,
    duracion_min: int | None = None,
) -> dict:
    """Crea la cita. Devuelve {'inicio': ..., 'fin': ..., 'link': ...}.

    Si la hora está ocupada, levanta ValueError y NO crea nada.
    """
    duracion = duracion_min or settings.duracion_cita_minutos
    if not hora_libre(inicio_iso, duracion):
        raise ValueError(f"La hora {inicio_iso} ya está ocupada en el calendario.")
    inicio = _a_datetime(inicio_iso)
    fin = inicio + timedelta(minutes=duracion)
    servicio = _servicio_calendar()
    evento = (
        servicio.events()
        .insert(
            calendarId=settings.calendar_id,
            body={
                "summary": f"Cita {nombre} — {telefono}",
                "description": f"Motivo: {motivo}\nOrigen: whatsapp (robot)",
                "start": {"dateTime": inicio.isoformat(), "timeZone": settings.timezone},
                "end": {"dateTime": fin.isoformat(), "timeZone": settings.timezone},
            },
        )
        .execute()
    )
    return {
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "link": evento.get("htmlLink", ""),
    }
