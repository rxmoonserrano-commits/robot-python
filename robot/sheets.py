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

import threading
import time

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
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()


def _invalidar_cache(pestana: str) -> None:
    """Borra la caché de una pestaña (después de escribir en ella)."""
    with _CACHE_LOCK:
        _CACHE.pop(pestana, None)


def leer_pestana(pestana: str) -> list[dict]:
    """Lee una pestaña y la devuelve como lista de filas (dict por columna).

    La primera fila son los encabezados. Las filas vacías se ignoran.
    Las lecturas se comparten 10 s en caché (ver arriba).
    """
    with _CACHE_LOCK:
        guardado = _CACHE.get(pestana)
        if guardado and time.monotonic() - guardado[0] < _CACHE_TTL_SEGUNDOS:
            return list(guardado[1])
    servicio = _servicio_sheets()
    resultado = (
        servicio.values()
        .get(spreadsheetId=settings.sheet_id, range=f"{pestana}!A1:Z1000")
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
        _CACHE[pestana] = (time.monotonic(), filas)
    return list(filas)


def agregar_fila(pestana: str, fila: list[str]) -> None:
    """Agrega una fila al final de una pestaña (sin borrar nada)."""
    servicio = _servicio_sheets()
    servicio.values().append(
        spreadsheetId=settings.sheet_id,
        range=f"{pestana}!A:Z",
        valueInputOption="USER_ENTERED",
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
        valueInputOption="USER_ENTERED",
        body={"values": [[fecha_iso]]},
    ).execute()
    _invalidar_cache("Control")


def leer_conocimiento() -> list[dict]:
    """Conocimiento: servicios, precios, horarios, políticas y FAQs del negocio."""
    return leer_pestana("Conocimiento")


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
        valueInputOption="USER_ENTERED",
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
        valueInputOption="USER_ENTERED",
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
def guardar_memoria_cliente(telefono: str, resumen: str = "", interes: str = "",
                            proxima_accion: str = "", preferencias: str = "") -> None:
    """Guarda la memoria del cliente en Clientes (K, L, N, O).

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
    if not nuevos:
        return
    valores = [
        nuevos.get("resumen_conversacion", str(fila.get("resumen_conversacion", "") or "")),
        nuevos.get("intereses", str(fila.get("intereses", "") or "")),
        str(fila.get("calificacion", "") or ""),
        nuevos.get("proxima_accion", str(fila.get("proxima_accion", "") or "")),
        nuevos.get("notas", str(fila.get("notas", "") or "")),
    ]
    servicio = _servicio_sheets()
    servicio.values().update(
        spreadsheetId=settings.sheet_id,
        range=f"Clientes!K{numero_fila}:O{numero_fila}",
        valueInputOption="USER_ENTERED",
        body={"values": [valores]},
    ).execute()
    _invalidar_cache("Clientes")


# --- Propuestas de cita (v2.5): que sobrevivan a un reinicio ---
# Las propuestas vivían solo en la memoria del servidor: si Render se
# reiniciaba de noche, el cliente tocaba Confirmar y el robot ya no
# sabía de qué cita hablaba. Ahora viven también en la pestaña
# Propuestas (una fila por teléfono, se borra al confirmarse).
# Columnas: telefono, nombre, motivo, fecha_cita, fecha_bonita, creado_en,
# apartado (v3.2: "si" si le apartaron el lugar), aparta_hasta (hasta cuándo).
_COLUMNAS_PROPUESTA = ["telefono", "nombre", "motivo", "fecha_cita",
                       "fecha_bonita", "creado_en", "apartado", "aparta_hasta"]


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
                range=f"Propuestas!A{i + 2}:H{i + 2}",
                valueInputOption="USER_ENTERED",
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
                range=f"Propuestas!A{i + 2}:H{i + 2}",
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
