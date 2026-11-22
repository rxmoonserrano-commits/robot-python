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

import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import settings
from .sheets import SCOPES


def _servicio_calendar():
    # (v3.1) Con tiempo límite de 30 s, igual que Sheets: una llamada
    # colgada a Google no puede dejar un lote atorado para siempre.
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_credentials_json, scopes=SCOPES
        )
    except (FileNotFoundError, ValueError, GoogleAuthError) as exc:
        raise RuntimeError(
            "No encontré las credenciales de Google. Revisa GOOGLE_CREDENTIALS_JSON "
            f"en tu .env (ahora apunta a: {settings.google_credentials_json})."
        ) from exc
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp

    http = AuthorizedHttp(creds, http=httplib2.Http(timeout=30))
    return build("calendar", "v3", http=http)


def _parse_fecha_iso(texto: str) -> datetime | None:
    """Parsea una fecha ISO con tolerancia (v3.4.11).

    Acepta lo normal y también lo que la hoja devolvía tras
    reinterpretar fechas ('2026-11-19 9:00:00', hora de un dígito):
    rellena la hora a dos dígitos. None si no se puede leer.
    """
    t = str(texto or "").strip().replace("Z", "+00:00")
    if not t:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(.*)$", t)
    if m:
        fecha, hora, minuto, segundo, resto = m.groups()
        t = f"{fecha}T{int(hora):02d}:{minuto}:{segundo or '00'}{resto}"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _a_datetime(fecha_iso: str) -> datetime:
    """Acepta '2026-11-14T10:00:00' y lo convierte a fecha con zona horaria."""
    fecha = _parse_fecha_iso(fecha_iso)
    if fecha is None:
        raise ValueError(f"Fecha no legible: {fecha_iso!r}")
    if fecha.tzinfo is None:
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


# Caché de huecos libres (v3.3): los huecos no cambian a cada segundo
# y cada cálculo cuesta una llamada a Calendar. 60 s es suficiente:
# dos mensajes seguidos del mismo cliente no vuelven a preguntar.
_HUECOS_TTL_SEGUNDOS = 60.0
_HUECOS_CACHE: dict[str, tuple[float, list[str]]] = {}


def proximos_huecos_libres(
    horarios: dict[int, tuple[int, int]],
    ahora: datetime,
    cantidad: int = 2,
    dias: int = 3,
    usar_cache: bool = True,
) -> list[str]:
    """Los próximos `cantidad` huecos libres, en hora en punto, dentro
    del horario del negocio, en los próximos `dias` días.

    `horarios` es el dict de logic.horarios_por_dia: {día de semana:
    (minuto de apertura, minuto de cierre)}. Devuelve fechas ISO
    (hora local del negocio). Una sola llamada a Calendar (freebusy
    del rango entero): no una por hueco. Si Calendar falla, devuelve
    [] y quien llama decide (el agente no inventa horas: el contexto
    dice que no hay huecos).

    La confirmación vuelve a revisar la hora (crear_cita): si un hueco
    se ocupó entre el cálculo y la confirmación, no se crea nada.
    """
    clave = f"{cantidad}:{dias}"
    if usar_cache:
        guardado = _HUECOS_CACHE.get(clave)
        if guardado and time.monotonic() - guardado[0] < _HUECOS_TTL_SEGUNDOS:
            return list(guardado[1])
    local = ahora.astimezone(ZoneInfo(settings.timezone)) if ahora.tzinfo else ahora.replace(tzinfo=ZoneInfo(settings.timezone))
    duracion = settings.duracion_cita_minutos
    inicio_rango = local
    fin_rango = local + timedelta(days=dias + 1)
    try:
        servicio = _servicio_calendar()
        ocupados = (
            servicio.freebusy()
            .query(
                body={
                    "timeMin": inicio_rango.isoformat(),
                    "timeMax": fin_rango.isoformat(),
                    "timeZone": settings.timezone,
                    "items": [{"id": settings.calendar_id}],
                }
            )
            .execute()
        )
        lista = ocupados.get("calendars", {}).get(settings.calendar_id, {}).get("busy", [])
        busy = [(_a_datetime(b["start"]), _a_datetime(b["end"])) for b in lista]
    except Exception:
        return []
    huecos: list[str] = []
    for adelanto in range(dias + 1):
        dia = local + timedelta(days=adelanto)
        horas = horarios.get(dia.weekday())
        if not horas:
            continue
        abre_min, cierra_min = horas
        for hora in range(24):
            inicio_min = hora * 60
            if inicio_min < abre_min or inicio_min + duracion > cierra_min:
                continue
            slot = dia.replace(hour=hora, minute=0, second=0, microsecond=0)
            if slot <= local:
                continue
            fin = slot + timedelta(minutes=duracion)
            if any(b_inicio < fin and slot < b_fin for b_inicio, b_fin in busy):
                continue
            huecos.append(slot.isoformat())
            if len(huecos) >= cantidad:
                break
        if len(huecos) >= cantidad:
            break
    if usar_cache:
        _HUECOS_CACHE[clave] = (time.monotonic(), list(huecos))
    return huecos


def proximos_huecos_por_profesional(
    profesionales: list[dict],
    ahora: datetime,
    cantidad: int = 2,
    dias: int = 3,
) -> list[dict]:
    """Huecos libres con nombre de profesional (v3.12, Sereno función 02).

    `profesionales` viene de sheets.leer_profesionales():
    [{"nombre": str, "horarios": {weekday: (abre_min, cierra_min)}}].
    Devuelve [{"inicio": iso, "profesional": nombre}] ordenados por
    hora, en hora en punto, dentro del horario de cada profesional y
    sin chocar con el calendario (una sola llamada freebusy, igual
    que la versión por clínica; la revisión es conservadora: un
    evento ocupado bloquea a todos, nunca se duplican citas).

    Sin profesionales o con error de Calendar devuelve []: quien
    llama cae a la agenda por clínica. La confirmación vuelve a
    revisar la hora (crear_cita), como siempre.
    """
    if not profesionales:
        return []
    clave = (
        f"pro:{cantidad}:{dias}:"
        + ",".join(sorted(p["nombre"] for p in profesionales))
    )
    guardado = _HUECOS_CACHE.get(clave)
    if guardado and time.monotonic() - guardado[0] < _HUECOS_TTL_SEGUNDOS:
        return [dict(h) for h in guardado[1]]
    local = ahora.astimezone(ZoneInfo(settings.timezone)) if ahora.tzinfo else ahora.replace(tzinfo=ZoneInfo(settings.timezone))
    duracion = settings.duracion_cita_minutos
    inicio_rango = local
    fin_rango = local + timedelta(days=dias + 1)
    try:
        servicio = _servicio_calendar()
        ocupados = (
            servicio.freebusy()
            .query(
                body={
                    "timeMin": inicio_rango.isoformat(),
                    "timeMax": fin_rango.isoformat(),
                    "timeZone": settings.timezone,
                    "items": [{"id": settings.calendar_id}],
                }
            )
            .execute()
        )
        lista = ocupados.get("calendars", {}).get(settings.calendar_id, {}).get("busy", [])
        busy = [(_a_datetime(b["start"]), _a_datetime(b["end"])) for b in lista]
    except Exception:
        return []
    huecos: list[dict] = []
    for adelanto in range(dias + 1):
        dia = local + timedelta(days=adelanto)
        for prof in profesionales:
            horas = prof.get("horarios", {}).get(dia.weekday())
            if not horas:
                continue
            abre_min, cierra_min = horas
            for hora in range(24):
                inicio_min = hora * 60
                if inicio_min < abre_min or inicio_min + duracion > cierra_min:
                    continue
                slot = dia.replace(hour=hora, minute=0, second=0, microsecond=0)
                if slot <= local:
                    continue
                fin = slot + timedelta(minutes=duracion)
                if any(b_inicio < fin and slot < b_fin for b_inicio, b_fin in busy):
                    continue
                huecos.append({"inicio": slot.isoformat(), "profesional": prof["nombre"]})
        if len(huecos) >= cantidad:
            break
    huecos.sort(key=lambda h: (h["inicio"], h["profesional"]))
    huecos = huecos[:cantidad]
    _HUECOS_CACHE[clave] = (time.monotonic(), [dict(h) for h in huecos])
    return huecos


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
    nota: str = "",
) -> dict:
    """Crea la cita. Devuelve {'inicio': ..., 'fin': ..., 'link': ...}.

    Si la hora está ocupada, levanta ValueError y NO crea nada.
    `nota` (v3.4.9) va en la descripción del evento (p. ej. el
    teléfono de registro que dio el cliente).
    """
    duracion = duracion_min or settings.duracion_cita_minutos
    if not hora_libre(inicio_iso, duracion):
        raise ValueError(f"La hora {inicio_iso} ya está ocupada en el calendario.")
    inicio = _a_datetime(inicio_iso)
    fin = inicio + timedelta(minutes=duracion)
    descripcion = f"Motivo: {motivo}\nOrigen: whatsapp (robot)"
    if nota:
        descripcion += f"\n{nota}"
    servicio = _servicio_calendar()
    evento = (
        servicio.events()
        .insert(
            calendarId=settings.calendar_id,
            body={
                "summary": f"Cita {nombre} — {telefono}",
                "description": descripcion,
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
