"""Google Sheets: el documento oficial del negocio.

La hoja "Robot WhatsApp — Documento oficial" tiene 6 pestañas:
Control, Conocimiento, Fotos oficiales, Conversaciones, Clientes, Reporte.

El robot SOLO sabe lo que está en Conocimiento, SOLO manda fotos de
Fotos oficiales, y registra todo en Conversaciones y Clientes.
Nada de datos reales en el código: solo nombres de pestañas y columnas.

Autenticación: cuenta de servicio de Google. Se crea en Google Cloud,
se descarga su archivo JSON y se comparte la hoja con su correo
(ver README, paso 3). El archivo JSON nunca se sube a ningún lado.
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from datetime import datetime, timezone

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import settings
from .registro import error as log_error

# Permisos mínimos: leer y escribir en Sheets, y ver/crear citas en Calendar.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
]


def _servicio_sheets():
    """Conecta con Google Sheets. Falla con un mensaje claro si no hay credenciales.

    (v3.1) Con tiempo límite de 30 s: antes, las llamadas a Google no
    tenían timeout y una llamada colgada podía dejar un lote atorado
    para siempre, sin rastro. El 12 de noviembre un lote se quedó más
    de 45 minutos sin responder ni fallar; con timeout, esa llamada
    falla a los 30 s y el robot contesta "dame un momento" como debe.
    """
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.google_credentials_json, scopes=SCOPES
        )
    except (FileNotFoundError, ValueError, GoogleAuthError) as exc:
        raise RuntimeError(
            "No encontré las credenciales de Google. Revisa GOOGLE_CREDENTIALS_JSON "
            f"en tu .env (ahora apunta a: {settings.google_credentials_json}). "
            "Ver README, paso 3."
        ) from exc
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp

    http = AuthorizedHttp(creds, http=httplib2.Http(timeout=30))
    return build("sheets", "v4", http=http).spreadsheets()


# --- Caché de lectura (v3.0) ---
# Antes, cada mensaje hacía unas 8-12 llamadas a Google: Clientes se
# leía tres veces (interruptor, fila del cliente, upsert) y
# Conversaciones dos, cada una abriendo su propia conexión. Lento, y
# con techo de cuota si el negocio crece. Ahora cada pestaña se guarda
# 10 segundos en memoria: todas las lecturas de un mismo mensaje
# comparten UNA llamada. 10 s es seguro: un mensaje se atiende en
# segundos, y cualquier escritura (agregar, actualizar, borrar) borra
# la caché de su pestaña al momento. Nadie lee datos viejos de más
# de 10 segundos, y nadie lee lo que el propio robot acaba de escribir.
_CACHE_TTL_SEGUNDOS = 10.0
_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()


def _clave_cache(pestana: str, spreadsheet_id: str | None = None) -> tuple[str, str]:
    return (spreadsheet_id or settings.sheet_id, pestana)


def _invalidar_cache(pestana: str) -> None:
    """Borra la caché de una pestaña (después de escribir en ella)."""
    with _CACHE_LOCK:
        _CACHE.pop(_clave_cache(pestana), None)


def leer_pestana(pestana: str, spreadsheet_id: str | None = None) -> list[dict]:
    """Lee una pestaña y la devuelve como lista de filas (dict por columna).

    La primera fila son los encabezados. Las filas vacías se ignoran.
    Las lecturas se comparten 10 s en caché (ver arriba). Con
    spreadsheet_id se lee de otra hoja (el documento maestro
    Negocios, v3.6); sin él, de la hoja operativa del negocio.
    """
    clave = _clave_cache(pestana, spreadsheet_id)
    with _CACHE_LOCK:
        guardado = _CACHE.get(clave)
        if guardado and time.monotonic() - guardado[0] < _CACHE_TTL_SEGUNDOS:
            return list(guardado[1])
    servicio = _servicio_sheets()
    resultado = (
        servicio.values()
        # (v3.20.4, auditoría de datos) Antes A1:Z1000: al pasar las
        # 1000 filas, Conversaciones perdía el historial viejo en
        # silencio y Clientes dejaba de ver clientes (duplicados).
        # 10000 filas cubre meses de operación; más allá, rotación
        # de la hoja (propuesta, no implementada).
        .get(spreadsheetId=clave[0], range=f"{pestana}!A1:Z10000")
        .execute()
    )
    valores = resultado.get("values", [])
    if not valores:
        filas: list[dict] = []
    else:
        encabezados = [h.strip() for h in valores[0]]
        filas = []
        for fila in valores[1:]:
            if not any(str(c).strip() for c in fila):
                continue
            filas.append({h: (fila[i] if i < len(fila) else "") for i, h in enumerate(encabezados)})
    with _CACHE_LOCK:
        _CACHE[clave] = (time.monotonic(), filas)
    return list(filas)


def _columna_letra(n: int) -> str:
    """1 -> A, 15 -> O, 27 -> AA... (letra de columna para un ancho dado)."""
    letra = ""
    while n > 0:
        n, resto = divmod(n - 1, 26)
        letra = chr(65 + resto) + letra
    return letra or "A"


def agregar_fila(pestana: str, fila: list[str]) -> None:
    """Agrega una fila al final de una pestaña (sin borrar nada).

    El rango del append se ancla al ancho real de la fila, no a A:Z:
    si la pestaña tiene datos a la derecha (p. ej. el panel resumen
    de Citas en Q:R), el append de Sheets lo toma como otra tabla y
    escribe las filas corridas en Q. Con el ancho exacto, la tabla
    detectada es la principal y la fila cae en su sitio.
    """
    servicio = _servicio_sheets()
    servicio.values().append(
        spreadsheetId=settings.sheet_id,
        range=f"{pestana}!A:{_columna_letra(len(fila))}",
        valueInputOption="RAW",
        body={"values": [fila]},
    ).execute()
    _invalidar_cache(pestana)


# --- Lecturas que usa el robot, una por pestaña ---


def leer_control() -> dict:
    """Control: una sola fila. Devuelve {'bot_activo': 'SI', 'ultima_respuesta_humana': ''}."""
    filas = leer_pestana("Control")
    if not filas:
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}
    return filas[0]


def actualizar_ultima_respuesta_humana(fecha_iso: str) -> None:
    """Anota en Control cuándo una persona atendió un chat (eso arranca la pausa de 2 h).

    La hoja Control solo tiene una fila de datos (fila 2), así que se escribe
    directo en la celda B2.
    """
    servicio = _servicio_sheets()
    servicio.values().update(
        spreadsheetId=settings.sheet_id,
        range="Control!B2",
        valueInputOption="RAW",
        body={"values": [[fecha_iso]]},
    ).execute()
    _invalidar_cache("Control")


def leer_conocimiento() -> list[dict]:
    """Conocimiento: servicios, precios, horarios, políticas y FAQs del negocio."""
    return leer_pestana("Conocimiento")


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


def duracion_servicio(motivo: str) -> int | None:
    """Duración en minutos de un servicio, desde Conocimiento (columna
    Duración_min, v3.9).

    Busca la fila de tipo servicio cuyo nombre coincida con el motivo
    (sin acentos, contención en cualquier dirección). None si no hay
    dato válido: el robot usa la duración por defecto (60).
    """
    objetivo = _normalizar(motivo)
    if not objetivo:
        return None
    try:
        filas = leer_conocimiento()
    except Exception:  # noqa: BLE001 - sin dato, se usa el default
        return None
    for f in filas:
        if str(f.get("tipo", "")).strip().lower() != "servicio":
            continue
        nombre = _normalizar(f.get("pregunta_o_servicio", ""))
        if nombre and (objetivo in nombre or nombre in objetivo):
            try:
                minutos = int(float(str(f.get("Duración_min", "") or "").strip()))
            except (ValueError, TypeError):
                return None
            return minutos if minutos > 0 else None
    return None


def _parse_rango_horas(texto: str) -> tuple[int, int] | None:
    """'09:00-18:00' -> (540, 1080). 'Cerrado', vacío o ilegible -> None."""
    m = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", str(texto or ""))
    if not m:
        return None
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    abre, cierra = h1 * 60 + m1, h2 * 60 + m2
    return (abre, cierra) if cierra > abre else None


def leer_profesionales() -> list[dict]:
    """Profesionales activos con su horario, desde la pestaña Profesionales (v3.12).

    Devuelve [{"nombre": str, "horarios": {weekday: (abre_min, cierra_min)}}]
    solo con los activos (Activo = Sí) y con horario legible. Sin pestaña
    o sin datos válidos devuelve []: la agenda sigue por clínica, como
    siempre (compatibilidad total con hojas viejas).
    """
    try:
        filas = leer_pestana("Profesionales")
    except Exception:  # noqa: BLE001 - sin pestaña, agenda por clínica
        return []
    resultado = []
    for f in filas:
        nombre = str(f.get("Nombre", "") or "").strip()
        activo = _normalizar(f.get("Activo", ""))
        if not nombre or activo not in ("si", "true", "1", "x"):
            continue
        horarios: dict[int, tuple[int, int]] = {}
        rango = _parse_rango_horas(f.get("Horario_lun_vie", ""))
        if rango:
            for dia in range(5):
                horarios[dia] = rango
        rango_sab = _parse_rango_horas(f.get("Horario_sab", ""))
        if rango_sab:
            horarios[5] = rango_sab
        if horarios:
            resultado.append({"nombre": nombre, "horarios": horarios})
    return resultado


# --- Espejo de citas (v3.9): la pestaña Citas como vista de solo lectura ---
# El dueño consulta ahí confirmadas, pendientes, canceladas y no-show
# sin entrar al calendario. La fuente de verdad sigue siendo el
# calendario: editar el espejo no agenda nada.
_CITAS_COLUMNAS = ["ID_Cita", "ID_Paciente", "Teléfono", "Servicio", "Profesional", "Fecha",
                   "Hora_inicio", "Hora_fin", "Estado", "Origen", "Recordatorio_enviado",
                   "Confirmado", "Notas", "Creado_por", "Última_actualización", "Urgencia"]


def registrar_cita_espejo(fila: dict) -> None:
    """Agrega una fila a la pestaña Citas (espejo de solo lectura, v3.9).

    Best-effort: si la hoja falla, solo queda en el registro; nunca
    rompe la respuesta al cliente.
    """
    try:
        agregar_fila("Citas", [str(fila.get(c, "") or "") for c in _CITAS_COLUMNAS])
        _invalidar_cache("Citas")
    except Exception as exc:  # noqa: BLE001
        log_error(f"[citas-espejo] No se pudo registrar la cita: {exc}")


def actualizar_cita_espejo(telefono: str, fecha_cita: str, estado: str | None = None,
                           notas: str | None = None,
                           recordatorio_enviado: str | None = None,
                           urgencia: str | None = None,
                           nueva_fecha: str | None = None,
                           nueva_hora_inicio: str | None = None,
                           nueva_hora_fin: str | None = None) -> None:
    """Actualiza el Estado (columna I), las Notas (columna M), el
    Recordatorio_enviado (columna K, v3.12), la Urgencia (columna P,
    v3.13) y/o la Fecha/Hora (columnas F/G/H, v3.15: mover la cita
    al adelantarla por urgencia) de la última cita espejo que
    coincida con teléfono + fecha (v3.9; las Notas se suman en v3.10
    para guardar los datos de la otra persona). Best-effort. Sin
    ningún dato, no hace nada.

    (v3.20.4, auditoría de datos) Antes hacía hasta 6 escrituras
    seguidas: si Google fallaba a la mitad, el espejo quedaba a
    medias (p. ej. Estado cambiado pero Notas viejas) sin rastro
    en la hoja. Ahora es UNA sola escritura atómica sobre F:P con
    los valores nuevos y los viejos intactos; si falla, queda un
    rastro en Diagnóstico además del registro del servidor."""
    try:
        if (estado is None and notas is None and recordatorio_enviado is None
                and urgencia is None and nueva_fecha is None
                and nueva_hora_inicio is None and nueva_hora_fin is None):
            return
        filas = leer_pestana("Citas")
        dia = str(fecha_cita or "")[:10]
        objetivo = str(telefono or "").strip()
        numero = None
        fila_vieja: dict = {}
        for i, f in enumerate(filas):
            if (str(f.get("Teléfono", "") or "").strip() == objetivo
                    and str(f.get("Fecha", "") or "")[:10] == dia):
                numero = i + 2  # +1 encabezado, +1 base 1
                fila_vieja = f
        if numero is None:
            return
        # Una sola escritura: F:P con lo nuevo encima de lo viejo.
        valores = [[
            str(nueva_fecha)[:10] if nueva_fecha is not None
            else str(fila_vieja.get("Fecha", "") or ""),
            str(nueva_hora_inicio) if nueva_hora_inicio is not None
            else str(fila_vieja.get("Hora_inicio", "") or ""),
            str(nueva_hora_fin) if nueva_hora_fin is not None
            else str(fila_vieja.get("Hora_fin", "") or ""),
            str(estado) if estado is not None
            else str(fila_vieja.get("Estado", "") or ""),
            str(fila_vieja.get("Origen", "") or ""),
            str(recordatorio_enviado) if recordatorio_enviado is not None
            else str(fila_vieja.get("Recordatorio_enviado", "") or ""),
            str(fila_vieja.get("Confirmado", "") or ""),
            str(notas) if notas is not None
            else str(fila_vieja.get("Notas", "") or ""),
            str(fila_vieja.get("Creado_por", "") or ""),
            str(fila_vieja.get("Última_actualización", "") or ""),
            str(urgencia) if urgencia is not None
            else str(fila_vieja.get("Urgencia", "") or ""),
        ]]
        servicio = _servicio_sheets()
        servicio.values().update(
            spreadsheetId=settings.sheet_id,
            range=f"Citas!F{numero}:P{numero}",
            valueInputOption="RAW",
            body={"values": valores},
        ).execute()
        _invalidar_cache("Citas")
    except Exception as exc:  # noqa: BLE001
        log_error(f"[citas-espejo] No se pudo actualizar la cita: {exc}")
        try:
            registrar_diagnostico(
                datetime.now(timezone.utc), "citas-espejo", "FALLO",
                str(exc)[:300], str(telefono or ""), "")
        except Exception:  # noqa: BLE001 - el rastro nunca rompe nada
            pass


def leer_citas_espejo() -> list[dict]:
    """Todas las filas de la pestaña Citas (espejo, v3.10).

    Lo usa el tope de 2 citas por número: cuenta las citas activas
    (Confirmada/Pendiente a futuro) de un teléfono. Si la pestaña no
    existe o la hoja falla, devuelve [].
    """
    try:
        return leer_pestana("Citas")
    except Exception:  # noqa: BLE001
        return []


def leer_configuracion() -> dict[str, str]:
    """Configuración por negocio (pestaña Configuración: clave | valor).

    Interruptores y personalización que Jose (o el dueño, con permiso)
    cambia desde la hoja sin tocar código: tono, saludo, agendar sí/no,
    enviar fotos sí/no, etc. Si la pestaña no existe o está vacía
    (la hoja actual, antes de esta versión), devuelve {} y el robot
    usa sus valores por defecto: nada se rompe por agregar la pestaña.
    """
    try:
        filas = leer_pestana("Configuración")
    except Exception:  # noqa: BLE001 - sin pestaña, sin configuración
        return {}
    cfg: dict[str, str] = {}
    for fila in filas:
        clave = str(fila.get("clave", "")).strip()
        if clave:
            cfg[clave] = str(fila.get("valor", "")).strip()
    return cfg


def leer_fotos_oficiales() -> list[dict]:
    """Fotos oficiales: la lista blanca. Solo estas URLs existen para el robot."""
    return leer_pestana("Fotos oficiales")


def leer_robot_activo(telefono: str) -> str:
    """Interruptor por cliente: lo que dice la columna robot_activo de Clientes.

    Devuelve "SI" o "NO". Si el cliente no está en la hoja, o la celda
    está en blanco, es "SI": el robot contesta por defecto. Solo un NO
    explícito lo apaga para ese cliente. La columna robot_activo vive
    en Clientes (columna P), nunca se escribe desde aquí, solo se lee:
    la pone el dueño o el cliente que ve la hoja.
    """
    for fila in leer_pestana("Clientes"):
        if str(fila.get("telefono", "")).strip() == str(telefono).strip():
            valor = str(fila.get("robot_activo", "") or "").strip().upper()
            return "NO" if valor in {"NO", "N", "FALSE", "FALSO"} else "SI"
    return "SI"


def leer_cliente(telefono: str) -> dict | None:
    """La fila de Clientes de un teléfono (con estatus y fecha_cita), o None."""
    for fila in leer_pestana("Clientes"):
        if str(fila.get("telefono", "")).strip() == str(telefono).strip():
            return fila
    return None


def cancelar_cita_cliente(telefono: str) -> None:
    """Limpia la cita de un cliente en Clientes: fecha_cita vacía y
    estatus de vuelta a "en conversacion". No borra la fila ni toca
    las columnas extra (resumen, calificación...)."""
    encontrado = _fila_cliente_por_telefono(telefono)
    if encontrado is None:
        return
    numero_fila, existente = encontrado
    servicio = _servicio_sheets()
    servicio.values().update(
        spreadsheetId=settings.sheet_id,
        range=f"Clientes!E{numero_fila}:G{numero_fila}",
        valueInputOption="RAW",
        body={"values": [[ "", existente.get("origen", "whatsapp"), "en conversacion" ]]},
    ).execute()
    _invalidar_cache("Clientes")


def leer_historial(telefono: str, limite: int = 20) -> list[dict]:
    """Últimos mensajes de un teléfono, incluido lo que dijo el humano en la pausa."""
    filas = leer_pestana("Conversaciones")
    del_telefono = [f for f in filas if str(f.get("telefono", "")) == str(telefono)]
    return del_telefono[-limite:]


# --- Escrituras: el registro de todo ---


def registrar_conversacion(
    fecha: str,
    telefono: str,
    quien_hablo: str,
    mensaje: str,
    robot_respondio: str,
    motivo: str = "",
) -> None:
    """Una fila por mensaje en Conversaciones. quien_hablo: cliente, robot o humano."""
    agregar_fila(
        "Conversaciones",
        [fecha, telefono, quien_hablo, mensaje, robot_respondio, motivo],
    )


# Columnas de Clientes, en orden: A fecha, B nombre, C teléfono,
# D motivo, E fecha_cita, F origen, G estatus, H handoff.
_COLUMNAS_CLIENTES = ["fecha", "nombre", "telefono", "motivo", "fecha_cita",
                      "origen", "estatus", "handoff"]
_PRIORIDAD_ESTATUS = {"en conversacion": 1, "calificado": 2, "agendado": 3}


def fusionar_cliente(existente: dict, nuevo: dict) -> list[str]:
    """Fusiona un cliente que ya existe con los datos nuevos: un cliente, una fila.

    Reglas, en simple:
    - La fecha es la más reciente (la nueva).
    - Nombre, motivo y fecha de cita: el nuevo si viene con algo, si no,
      se queda lo que ya había.
    - Estatus: nunca baja. "agendado" vale más que "calificado", y este
      más que "en conversacion". Una cita confirmada no se borra porque
      el cliente vuelva a escribir.
    - Handoff: si alguna vez fue "si", se queda en "si".
    Es una función pura (sin internet), así se prueba sola.
    """
    viejo = {k: str(existente.get(k, "") or "") for k in _COLUMNAS_CLIENTES}
    dato = {k: str(nuevo.get(k, "") or "") for k in _COLUMNAS_CLIENTES}
    estatus_viejo = viejo["estatus"].strip().lower()
    estatus_nuevo = dato["estatus"].strip().lower()
    estatus = (
        estatus_nuevo
        if _PRIORIDAD_ESTATUS.get(estatus_nuevo, 0) >= _PRIORIDAD_ESTATUS.get(estatus_viejo, 0)
        else estatus_viejo
    )
    return [
        dato["fecha"] or viejo["fecha"],
        dato["nombre"] or viejo["nombre"],
        viejo["telefono"] or dato["telefono"],
        dato["motivo"] or viejo["motivo"],
        dato["fecha_cita"] or viejo["fecha_cita"],
        dato["origen"] or viejo["origen"],
        estatus,
        "si" if {"si", "sí"} & {viejo["handoff"].strip().lower(), dato["handoff"].strip().lower()} else "no",
    ]


def _fila_cliente_por_telefono(telefono: str) -> tuple[int, dict] | None:
    """Busca un teléfono en Clientes. Devuelve (número de fila, fila) o None.

    La fila 1 son los encabezados, así que la primera fila de datos es la 2.
    (v3.0) Lee por leer_pestana, que comparte la caché: antes hacía su
    propia llamada a la hoja, así que Clientes se leía una vez más por
    cada mensaje.
    """
    for i, fila in enumerate(leer_pestana("Clientes")):
        if str(fila.get("telefono", "")).strip() == str(telefono).strip():
            completa = {k: str(fila.get(k, "") or "") for k in _COLUMNAS_CLIENTES}
            return i + 2, completa
    return None


def registrar_cliente(
    fecha: str,
    nombre: str,
    telefono: str,
    motivo: str,
    fecha_cita: str = "",
    origen: str = "whatsapp",
    estatus: str = "en conversacion",
    handoff: str = "no",
) -> None:
    """Registra un cliente calificado en Clientes, sin duplicarlo.

    Si el teléfono ya existe, actualiza SU fila (fusionar_cliente);
    si no, agrega una fila nueva. Un cliente, una fila: así la hoja
    que ve el cliente no se llena de repetidos y los contadores cuentan
    clientes, no mensajes. Las columnas extra (I en adelante: resumen,
    intereses, calificación...) no se tocan: solo se escribe A:H.
    """
    nuevo = {"fecha": fecha, "nombre": nombre, "telefono": telefono,
             "motivo": motivo, "fecha_cita": fecha_cita, "origen": origen,
             "estatus": estatus, "handoff": handoff}
    encontrado = _fila_cliente_por_telefono(telefono)
    if encontrado is None:
        agregar_fila(
            "Clientes",
            [fecha, nombre, telefono, motivo, fecha_cita, origen, estatus, handoff],
        )
        return
    numero_fila, existente = encontrado
    fusionada = fusionar_cliente(existente, nuevo)
    servicio = _servicio_sheets()
    servicio.values().update(
        spreadsheetId=settings.sheet_id,
        range=f"Clientes!A{numero_fila}:H{numero_fila}",
        valueInputOption="RAW",
        body={"values": [fusionada]},
    ).execute()
    _invalidar_cache("Clientes")


# --- Memoria del cliente (v3.2): lo que el robot aprendió ---
# Las columnas I en adelante de Clientes (resumen, intereses,
# calificación, próxima acción, notas) existían desde el rediseño
# pero nadie las llenaba: el robot no recordaba nada de un día a
# otro. Ahora el agente devuelve lo que aprendió en su JSON y esto
# lo guarda. Solo se escribe lo nuevo: un campo vacío NO borra lo
# que ya había. Las preferencias se acumulan ("solo en las mañanas;
# prefiere sábados"), sin repetir lo que ya estaba.
# Columnas: K resumen_conversacion, L intereses, N proxima_accion,
# O notas. La M (calificacion) es del dueño y no se toca.
# (v3.20.3) Columna de miedos / sensibilidades en Clientes. Se
# agrega AL FINAL (W): ninguna lectura ni escritura posicional la
# toca (K/L/N/O memoria, M calificación de Jose, P robot_activo).
# El código la lee por nombre de encabezado: si la hoja aún no la
# tiene, simplemente no se usa (los miedos siguen en el resumen).
_COL_MIEDOS = "Miedos / sensibilidades"


def guardar_memoria_cliente(telefono: str, resumen: str = "", interes: str = "",
                            proxima_accion: str = "", preferencias: str = "",
                            miedos: str = "") -> None:
    """Guarda la memoria del cliente en Clientes (K, L, N, O y W).

    No hace nada si no hay nada nuevo, y no hace nada si el teléfono
    no tiene fila (el cliente se registra primero por otro lado).
    """
    encontrado = _fila_cliente_por_telefono(telefono)
    if encontrado is None:
        return
    numero_fila, _ = encontrado
    filas = leer_pestana("Clientes")
    fila = filas[numero_fila - 2] if 0 <= numero_fila - 2 < len(filas) else {}
    nuevos: dict[str, str] = {}
    if str(resumen or "").strip():
        nuevos["resumen_conversacion"] = str(resumen).strip()[:300]
    if str(interes or "").strip():
        nuevos["intereses"] = str(interes).strip()[:150]
    if str(proxima_accion or "").strip():
        nuevos["proxima_accion"] = str(proxima_accion).strip()[:200]
    if str(preferencias or "").strip():
        viejo = str(fila.get("notas", "") or "").strip()
        nuevo_pref = str(preferencias).strip()[:150]
        if nuevo_pref.lower() not in viejo.lower():
            nuevos["notas"] = (
                (viejo + "; " + nuevo_pref).strip("; ")[:300] if viejo else nuevo_pref
            )
    # (v3.20.3) Miedos: se acumulan como las preferencias (si ya
    # está, no se duplica) y se escriben en la columna W, aparte.
    # Si la hoja aún no tiene el encabezado, no se escribe nada
    # (compatibilidad hacia atrás: el miedo sigue en el resumen).
    miedos_nuevo: str | None = None
    if str(miedos or "").strip() and _COL_MIEDOS in fila:
        viejo_m = str(fila.get(_COL_MIEDOS, "") or "").strip()
        nuevo_m = str(miedos).strip()[:150]
        if nuevo_m.lower() not in viejo_m.lower():
            miedos_nuevo = (
                (viejo_m + "; " + nuevo_m).strip("; ")[:300] if viejo_m else nuevo_m
            )
    if not nuevos and not miedos_nuevo:
        return
    # (v3.20.4, auditoría de datos) Antes, si la escritura de W
    # fallaba después de la de K:O, la excepción subía y el llamador
    # la tragaba en silencio: memoria a medias sin rastro en ningún
    # lado. Ahora cualquier fallo deja un rastro en Diagnóstico y
    # no lanza (la memoria es best-effort: la respuesta al cliente
    # ya salió).
    try:
        servicio = _servicio_sheets()
        if nuevos:
            valores = [
                nuevos.get("resumen_conversacion", str(fila.get("resumen_conversacion", "") or "")),
                nuevos.get("intereses", str(fila.get("intereses", "") or "")),
                str(fila.get("calificacion", "") or ""),
                nuevos.get("proxima_accion", str(fila.get("proxima_accion", "") or "")),
                nuevos.get("notas", str(fila.get("notas", "") or "")),
            ]
            servicio.values().update(
                spreadsheetId=settings.sheet_id,
                range=f"Clientes!K{numero_fila}:O{numero_fila}",
                valueInputOption="RAW",
                body={"values": [valores]},
            ).execute()
        if miedos_nuevo:
            servicio.values().update(
                spreadsheetId=settings.sheet_id,
                range=f"Clientes!W{numero_fila}",
                valueInputOption="RAW",
                body={"values": [[miedos_nuevo]]},
            ).execute()
    except Exception as exc:  # noqa: BLE001 - la memoria nunca rompe nada
        log_error(f"[memoria] No se pudo guardar la memoria de {telefono}: {exc}")
        try:
            registrar_diagnostico(
                datetime.now(timezone.utc), "memoria", "FALLO",
                str(exc)[:300], str(telefono or ""), "")
        except Exception:  # noqa: BLE001 - el rastro nunca rompe nada
            pass
        return
    _invalidar_cache("Clientes")


# --- Propuestas de cita (v2.5): que sobrevivan a un reinicio ---
# Las propuestas vivían solo en la memoria del servidor: si Render se
# reiniciaba de noche, el cliente tocaba Confirmar y el robot ya no
# sabía de qué cita hablaba. Ahora viven también en la pestaña
# Propuestas (una fila por teléfono, se borra al confirmarse).
# Columnas: telefono, nombre, motivo, fecha_cita, fecha_bonita, creado_en,
# apartado (v3.2: "si" si le apartaron el lugar), aparta_hasta (hasta cuándo),
# extra_json (v3.10: JSON con nombre_paciente, relacion_paciente y la
# segunda cita "cita2" si hay dos; vacío en propuestas de una cita).
_COLUMNAS_PROPUESTA = ["telefono", "nombre", "motivo", "fecha_cita",
                       "fecha_bonita", "creado_en", "apartado", "aparta_hasta",
                       "extra_json"]


def registrar_diagnostico(fecha, componente: str, estado: str, detalle: str,
                          telefono: str = "", contexto: str = "") -> None:
    """Escribe una fila en la pestaña Diagnóstico (v2.7).

    Es el "parte de salud" del robot, para que el dueño (o su
    asistente) vea qué le duele sin entrar a los registros de Render:
    la autoprueba de Gemini al arrancar, cada vez que Gemini falla,
    cada vez que WhatsApp rechaza un envío. Columnas: fecha,
    componente, estado, detalle, telefono, contexto.
    Best-effort: si la hoja falla, solo queda en el registro.
    """
    try:
        agregar_fila("Diagnóstico", [
            fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
            str(componente), str(estado), str(detalle)[:500],
            str(telefono), str(contexto)[:300],
        ])
    except Exception as exc:  # noqa: BLE001 - el diagnóstico nunca rompe nada
        log_error(f"[diagnostico] No pude escribir en la hoja: {exc}")


def leer_propuestas() -> list[dict]:
    """Todas las propuestas guardadas. Si la pestaña no existe aún, []."""
    try:
        return leer_pestana("Propuestas")
    except Exception:
        return []


def guardar_propuesta(telefono: str, propuesta: dict) -> None:
    """Guarda o actualiza la propuesta de un teléfono (una fila por teléfono).

    (v3.0) Busca por leer_pestana, que comparte la caché: antes hacía
    su propia llamada a la hoja.
    """
    fila_dato = [str(propuesta.get(c, "") or "") for c in _COLUMNAS_PROPUESTA]
    fila_dato[0] = str(telefono)
    for i, fila in enumerate(leer_pestana("Propuestas")):
        if str(fila.get("telefono", "")).strip() == str(telefono).strip():
            servicio = _servicio_sheets()
            servicio.values().update(
                spreadsheetId=settings.sheet_id,
                range=f"Propuestas!A{i + 2}:I{i + 2}",
                valueInputOption="RAW",
                body={"values": [fila_dato]},
            ).execute()
            _invalidar_cache("Propuestas")
            return
    agregar_fila("Propuestas", fila_dato)


def borrar_propuesta(telefono: str) -> None:
    """Borra la propuesta de un teléfono (se confirmó, se cambió o se canceló)."""
    for i, fila in enumerate(leer_pestana("Propuestas")):
        if str(fila.get("telefono", "")).strip() == str(telefono).strip():
            servicio = _servicio_sheets()
            servicio.values().clear(
                spreadsheetId=settings.sheet_id,
                range=f"Propuestas!A{i + 2}:I{i + 2}",
            ).execute()
            _invalidar_cache("Propuestas")
            return


def guardar_reporte(
    semana: str,
    mensajes_atendidos: int,
    clientes_calificados: int,
    citas_agendadas: int,
    handoffs: int,
    resumen: str,
) -> None:
    """Una fila por semana en Reporte. Así se compara semana con semana."""
    agregar_fila(
        "Reporte",
        [
            semana,
            str(mensajes_atendidos),
            str(clientes_calificados),
            str(citas_agendadas),
            str(handoffs),
            resumen,
        ],
    )
