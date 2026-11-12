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
