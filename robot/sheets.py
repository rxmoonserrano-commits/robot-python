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

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import settings

# Permisos mínimos: leer y escribir en Sheets, y ver/crear citas en Calendar.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
]


def _servicio_sheets():
    """Conecta con Google Sheets. Falla con un mensaje claro si no hay credenciales."""
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
    return build("sheets", "v4", credentials=creds).spreadsheets()


def leer_pestana(pestana: str) -> list[dict]:
    """Lee una pestaña y la devuelve como lista de filas (dict por columna).

    La primera fila son los encabezados. Las filas vacías se ignoran.
    """
    servicio = _servicio_sheets()
    resultado = (
        servicio.values()
        .get(spreadsheetId=settings.sheet_id, range=f"{pestana}!A1:Z1000")
        .execute()
    )
    valores = resultado.get("values", [])
    if not valores:
        return []
    encabezados = [h.strip() for h in valores[0]]
    filas = []
    for fila in valores[1:]:
        if not any(str(c).strip() for c in fila):
            continue
        filas.append({h: (fila[i] if i < len(fila) else "") for i, h in enumerate(encabezados)})
    return filas


def agregar_fila(pestana: str, fila: list[str]) -> None:
    """Agrega una fila al final de una pestaña (sin borrar nada)."""
    servicio = _servicio_sheets()
    servicio.values().append(
        spreadsheetId=settings.sheet_id,
        range=f"{pestana}!A:Z",
        valueInputOption="USER_ENTERED",
        body={"values": [fila]},
    ).execute()


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


def leer_conocimiento() -> list[dict]:
    """Conocimiento: servicios, precios, horarios, políticas y FAQs del negocio."""
    return leer_pestana("Conocimiento")


def leer_fotos_oficiales() -> list[dict]:
    """Fotos oficiales: la lista blanca. Solo estas URLs existen para el robot."""
    return leer_pestana("Fotos oficiales")


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
    """
    servicio = _servicio_sheets()
    resultado = (
        servicio.values()
        .get(spreadsheetId=settings.sheet_id, range="Clientes!A2:H1000")
        .execute()
    )
    for i, fila in enumerate(resultado.get("values", [])):
        if len(fila) < 3:
            continue
        if str(fila[2]).strip() == str(telefono).strip():
            completa = list(fila) + [""] * (8 - len(fila))
            return i + 2, dict(zip(_COLUMNAS_CLIENTES, completa))
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
