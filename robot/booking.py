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
import threading
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


def _ocupaciones(respuesta: dict) -> list:
    """No interpretar un error parcial de freebusy como calendario libre."""
    calendario = respuesta.get("calendars", {}).get(settings.calendar_id)
    if not isinstance(calendario, dict) or calendario.get("errors"):
        raise RuntimeError("Calendar no pudo confirmar la disponibilidad")
    ocupados = calendario.get("busy")
    if not isinstance(ocupados, list):
        raise RuntimeError("Calendar devolvió disponibilidad incompleta")
    return ocupados


# Serializa creaciones en este proceso; Calendar no ofrece una reserva
# transaccional frente a ediciones externas u otras instancias.
_CANDADO_RESERVAS = threading.Lock()


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
    lista = _ocupaciones(ocupados)
    return len(lista) == 0


# Caché de huecos libres (v3.3): los huecos no cambian a cada segundo
# y cada cálculo cuesta una llamada a Calendar. 60 s es suficiente:
# dos mensajes seguidos del mismo cliente no vuelven a preguntar.
_HUECOS_TTL_SEGUNDOS = 60.0
_HUECOS_CACHE_MAX = 128
_HUECOS_CACHE: dict[str, tuple[float, list]] = {}
_HUECOS_CACHE_LOCK = threading.RLock()
_HUECOS_CACHE_GENERACION = 0


def _copiar_huecos(huecos: list) -> list:
    return [dict(h) if isinstance(h, dict) else h for h in huecos]


def _cache_huecos_leer(clave: str) -> tuple[list | None, int]:
    with _HUECOS_CACHE_LOCK:
        guardado = _HUECOS_CACHE.get(clave)
        if guardado and time.monotonic() - guardado[0] < _HUECOS_TTL_SEGUNDOS:
            return _copiar_huecos(guardado[1]), _HUECOS_CACHE_GENERACION
        _HUECOS_CACHE.pop(clave, None)
        return None, _HUECOS_CACHE_GENERACION


def _cache_huecos_guardar(clave: str, huecos: list, generacion: int) -> None:
    with _HUECOS_CACHE_LOCK:
        # Una reserva/cancelación pudo invalidar el resultado mientras
        # la consulta de Calendar estaba en curso; no guardar ese dato.
        if generacion != _HUECOS_CACHE_GENERACION:
            return
        actual = time.monotonic()
        for vieja, (creada, _) in list(_HUECOS_CACHE.items()):
            if actual - creada >= _HUECOS_TTL_SEGUNDOS:
                _HUECOS_CACHE.pop(vieja, None)
        _HUECOS_CACHE[clave] = (actual, _copiar_huecos(huecos))
        while len(_HUECOS_CACHE) > _HUECOS_CACHE_MAX:
            mas_antigua = min(_HUECOS_CACHE, key=lambda k: _HUECOS_CACHE[k][0])
            _HUECOS_CACHE.pop(mas_antigua, None)


def _cache_huecos_invalidar() -> None:
    global _HUECOS_CACHE_GENERACION
    with _HUECOS_CACHE_LOCK:
        _HUECOS_CACHE.clear()
        _HUECOS_CACHE_GENERACION += 1


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
    del rango entero): no una por hueco. Si Calendar falla, propaga
    el error: no equivale a una agenda sin huecos.

    La confirmación vuelve a revisar la hora (crear_cita): si un hueco
    se ocupó entre el cálculo y la confirmación, no se crea nada.
    """
    if cantidad <= 0:
        return []
    # Los horarios y el minuto actual forman parte de la consulta: no
    # reutilizar un hueco pasado ni horarios que el dueño acaba de editar.
    clave = (f"{settings.calendar_id}:{settings.timezone}:{settings.duracion_cita_minutos}:"
             f"{ahora.isoformat(timespec='minutes')}:{cantidad}:{dias}:"
             f"{sorted(horarios.items())}")
    guardado, generacion = _cache_huecos_leer(clave)
    if usar_cache and guardado is not None:
        return guardado
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
        lista = _ocupaciones(ocupados)
        busy = [(_a_datetime(b["start"]), _a_datetime(b["end"])) for b in lista]
    except Exception as exc:
        raise RuntimeError("No se pudo consultar disponibilidad en Calendar") from exc
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
        _cache_huecos_guardar(clave, huecos, generacion)
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

    Sin profesionales devuelve []; un error de Calendar se propaga.
    La confirmación vuelve a revisar la hora (crear_cita).
    """
    if not profesionales or cantidad <= 0:
        return []
    clave = (
        f"pro:{settings.calendar_id}:{settings.timezone}:{settings.duracion_cita_minutos}:"
        f"{ahora.isoformat(timespec='minutes')}:{cantidad}:{dias}:"
        + repr(sorted((str(p.get("nombre", "")), sorted(p.get("horarios", {}).items()))
                      for p in profesionales))
    )
    guardado, generacion = _cache_huecos_leer(clave)
    if guardado is not None:
        return guardado
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
        lista = _ocupaciones(ocupados)
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
    _cache_huecos_guardar(clave, huecos, generacion)
    return huecos


def _eventos_del_dia(servicio, inicio: datetime) -> list:
    """Eventos del calendario en el día de `inicio` (v3.20.4).

    Lo comparten cancelar_cita y existe_cita: una sola forma de
    listar el día, para que no diverjan.
    """
    local = inicio.astimezone(ZoneInfo(settings.timezone))
    dia_inicio = local.replace(hour=0, minute=0, second=0, microsecond=0)
    dia_fin = dia_inicio + timedelta(days=1)
    argumentos = {
        "calendarId": settings.calendar_id,
        "timeMin": dia_inicio.isoformat(),
        "timeMax": dia_fin.isoformat(),
        "singleEvents": True,
    }
    eventos = []
    tokens_vistos = set()
    while True:
        pagina = servicio.events().list(**argumentos).execute()
        if not isinstance(pagina, dict) or not isinstance(pagina.get("items", []), list):
            raise RuntimeError("Calendar devolvió una lista de eventos inválida")
        eventos.extend(pagina.get("items", []))
        token = pagina.get("nextPageToken")
        if not token:
            return eventos
        if not isinstance(token, str) or token in tokens_vistos:
            raise RuntimeError("Calendar devolvió una paginación inválida")
        tokens_vistos.add(token)
        argumentos["pageToken"] = token


def _evento_de_cita(evento: dict, telefono: str, inicio: datetime) -> bool:
    """Solo el evento exacto de este teléfono y este instante es evidencia."""
    if not isinstance(evento, dict):
        return False
    titulo = str(evento.get("summary", ""))
    if not titulo.startswith("Cita ") or not titulo.endswith(f" — {telefono}"):
        return False
    try:
        comienzo = (evento.get("start") or {}).get("dateTime", "")
        return _a_datetime(comienzo) == inicio
    except (TypeError, ValueError, AttributeError):
        return False


def cancelar_cita(telefono: str, fecha_cita_iso: str) -> bool:
    """Borra únicamente el evento inequívoco de ese teléfono y hora.

    Los eventos del robot terminan en « — teléfono». Si hay más de una
    coincidencia se requiere intervención humana: no se adivina cuál.
    """
    if not str(telefono).isdigit():
        raise ValueError("Teléfono inválido")
    inicio = _a_datetime(fecha_cita_iso)
    servicio = _servicio_calendar()
    eventos = _eventos_del_dia(servicio, inicio)
    coincidencias = [evento for evento in eventos
                     if _evento_de_cita(evento, str(telefono), inicio)]
    if len(coincidencias) > 1:
        raise ValueError("Hay varias citas coincidentes; se necesita revisión humana")
    if not coincidencias:
        return False
    _cache_huecos_invalidar()
    try:
        servicio.events().delete(
            calendarId=settings.calendar_id, eventId=coincidencias[0]["id"]
        ).execute()
    finally:
        # Incluso si se corta la red, Calendar pudo haber aplicado el borrado.
        _cache_huecos_invalidar()
    return True


def existe_cita(telefono: str, fecha_iso: str) -> bool:
    """¿Ya existe en el calendario una cita de este teléfono en esa
    fecha/hora? (v3.20.4, reconciliación al arrancar).

    Busca los eventos del día cuyo título trae el teléfono y cuya
    hora de inicio coincide. Solo devuelve True con evidencia
    positiva: si algo falla, levanta la excepción y el llamador
    decide (la reconciliación la trata como "sin evidencia").
    """
    if not str(telefono).isdigit():
        raise ValueError("Teléfono inválido")
    inicio = _a_datetime(fecha_iso)
    servicio = _servicio_calendar()
    eventos = _eventos_del_dia(servicio, inicio)
    return any(_evento_de_cita(evento, str(telefono), inicio) for evento in eventos)


def crear_cita(
    nombre: str,
    telefono: str,
    motivo: str,
    inicio_iso: str,
    duracion_min: int | None = None,
    nota: str = "",
) -> dict:
    """Serializa las reservas de esta instancia antes de consultar Calendar."""
    with _CANDADO_RESERVAS:
        return _crear_cita(nombre, telefono, motivo, inicio_iso, duracion_min, nota)


def _crear_cita(
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
    _cache_huecos_invalidar()
    try:
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
    finally:
        # El resultado puede ser incierto aunque la petición haya fallado.
        _cache_huecos_invalidar()
    return {
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "link": evento.get("htmlLink", ""),
    }
