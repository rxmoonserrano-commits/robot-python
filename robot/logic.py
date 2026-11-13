"""El cerebro del robot: el flujo completo, paso a paso.

atender_mensaje recibe UN mensaje (o un lote ya juntado) y decide:
frenos (botón global, pausa humana, interruptor por cliente) →
registro → visto y "escribiendo..." → confirmación de cita por texto
→ cambio/cancelación → agente (con estado y revisor) → botones de
confirmación → registro en Conversaciones y Clientes.

La historia de cada versión vive en CHANGELOG.md, no aquí: este
archivo describe lo que el robot hace HOY, no lo que hacía en la v2.

Para probarlo sin internet, atender_mensaje recibe un objeto
`dependencias` con los servicios (Sheets, agente, WhatsApp, Calendar,
correo). En producción son los reales; en las pruebas son falsos.
La lógica es la misma.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .agent import RespuestaAgente, preguntar_agente
from .config import settings
from .estado import estado_cliente
from .revision import revisar_respuesta
from .registro import aviso as log_aviso
from .ritmo import enviar_con_ritmo

PAUSA = timedelta(hours=2)

# Botones que se muestran al proponer una cita (id, título).
BOTONES_CITA = [
    ("confirmar_cita", "Confirmar"),
    ("cambiar_hora", "Cambiar hora"),
    ("hablar_persona", "Hablar con persona"),
]

# Citas propuestas esperando que el cliente toque un botón (o diga "sí").
# Viven en memoria Y en la pestaña Propuestas de la hoja (v2.5): si el
# servidor se reinicia, se recuperan al arrancar (ver cargar_propuestas).
_CITAS_PENDIENTES: dict[str, dict] = {}

def _guardar_propuesta(deps: Dependencias, telefono: str, propuesta: dict) -> None:
    """Guarda una propuesta en memoria Y en la hoja (v2.5).

    La hoja es el respaldo: si Render se reinicia de noche, al
    arrancar se recuperan (ver cargar_propuestas) y el cliente puede
    confirmar igual. Si la hoja falla, la memoria sigue valiendo.
    """
    _CITAS_PENDIENTES[telefono] = propuesta
    guardar = getattr(deps, "guardar_propuesta", None)
    if guardar is not None:
        try:
            guardar(telefono, propuesta)
        except Exception:
            pass  # la memoria sigue valiendo; la hoja es respaldo


def _borrar_propuesta(deps: Dependencias, telefono: str) -> None:
    """Borra una propuesta de memoria Y de la hoja (se confirmó, cambió o canceló)."""
    _CITAS_PENDIENTES.pop(telefono, None)
    borrar = getattr(deps, "borrar_propuesta", None)
    if borrar is not None:
        try:
            borrar(telefono)
        except Exception:
            pass


def cargar_propuestas(deps: Dependencias) -> int:
    """Al arrancar el servidor: recupera las propuestas guardadas en la hoja.

    Devuelve cuántas recuperó. Sin esto, un reinicio de Render de noche
    dejaba al cliente con botones que ya no llevaban a ningún lado.
    """
    leer = getattr(deps, "leer_propuestas", None)
    if leer is None:
        return 0
    try:
        filas = leer() or []
    except Exception:
        return 0
    n = 0
    for fila in filas:
        telefono = str(fila.get("telefono", "") or "").strip()
        if not telefono or not str(fila.get("fecha_cita", "") or "").strip():
            continue
        _CITAS_PENDIENTES[telefono] = {
            k: str(fila.get(k, "") or "")
            for k in ("nombre", "motivo", "fecha_cita", "fecha_bonita", "creado_en")
        }
        n += 1
    return n


# Una propuesta solo se confirma con un "sí" por texto si es reciente
# (48 h). Así un "sí" de otra conversación, meses después, no agenda
# una cita vieja por error.
_VIGENCIA_PROPUESTA = timedelta(hours=48)


def _sin_acentos(texto: str) -> str:
    """Quita acentos y deja minúsculas: 'sí' → 'si', 'Está' → 'esta'."""
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().strip()


def _es_afirmacion(texto: str) -> bool:
    """¿El cliente está diciendo que sí a la cita propuesta?

    Solo frases cortas y claras ("sí", "sí, me va", "claro", "perfecto",
    "confirmo"). Un "sí, mejor el sábado" NO es afirmación: tiene
    "mejor" y pide otro día, así que va al agente, no a confirmar.
    """
    # Se quitan comas y puntos: "Sí, me va" debe leerse como "si me va".
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto)).strip()
    normal = re.sub(r"\s+", " ", normal)
    if not normal:
        return False
    if any(p in normal for p in ("mejor", "otro dia", "otra hora", "cambiar", " no ")):
        return False
    if normal.startswith("no"):
        return False
    palabras = normal.split()
    if len(palabras) > 4:
        return False
    if palabras[0] in ("si", "claro", "perfecto", "ok", "confirmo", "va", "sale", "de", "me"):
        return True
    return normal in ("si me va", "si me va esa fecha", "si esta bien", "estoy de acuerdo",
                       "de acuerdo", "me va", "me parece bien", "esta bien")


def _confirmar_cita_propuesta(deps: Dependencias, telefono: str, nombre: str,
                              fecha: str, con_ritmo: bool = True) -> dict:
    """Crea la cita de una propuesta guardada y manda la confirmación bonita.

    La usan el botón Confirmar y el "sí" por texto: el mismo resultado
    por los dos caminos. Si la hora ya se ocupó, avisa y no crea nada.
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if not propuesta:
        mensaje = "Claro. ¿Qué necesitas? Cuéntame y te ayudo."
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        return {"respondio": True, "motivo": "sin propuesta", "handoff": False}
    try:
        cita = deps.crear_cita(
            propuesta["nombre"], telefono, propuesta["motivo"], propuesta["fecha_cita"]
        )
    except Exception:
        _borrar_propuesta(deps, telefono)
        mensaje = (
            "Esa hora ya se ocupó, perdón. ¿Qué otro día y hora "
            "te vienen mejor? Te la agendo enseguida."
        )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "hora ocupada")
        return {"respondio": True, "motivo": "hora ocupada", "handoff": False}
    _borrar_propuesta(deps, telefono)
    mensaje = (
        f"Listo, {propuesta['nombre']}. Tu cita quedó para el "
        f"{propuesta['fecha_bonita']}. Dura {settings.duracion_cita_minutos} minutos.\n\n"
        f"Si necesitas cambiarla, escríbeme el nuevo día y hora y la reacomodamos."
    )
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", propuesta["motivo"])
    deps.registrar_cliente(
        fecha, propuesta["nombre"], telefono, propuesta["motivo"],
        propuesta["fecha_cita"], "whatsapp", "agendado", "no",
    )
    return {"respondio": True, "handoff": False, "cita": cita}


# --- Cambiar / cancelar cita (v2.4) ---

_PALABRAS_CANCELAR = ("cancelar", "cancela", "anular", "ya no quiero la cita")
_PALABRAS_CAMBIAR = (
    "cambiar", "reprogramar", "reagendar", "mover la cita", "mejor no",
    "prefiero otra", "otra hora", "otro dia", "otro día", "no quiero",
    "no me va", "no me sirve",
)


def _intencion_cambio(texto: str, hay_propuesta: bool = False) -> str | None:
    """¿El cliente quiere cambiar o cancelar su cita? Devuelve "cambiar",
    "cancelar" o None.

    Se lee el mensaje completo, no una sola palabra: "disculpe, mejor
    no, ¿si deseo cambiar la cita puedo?" es cambiar, aunque empiece
    con "disculpe". Un "otra" solo, con una propuesta pendiente, es
    "prefiero otra fecha" (cambiar). Sin propuesta ni cita, "otra" no
    es nada: va al agente, que pregunta qué otra cosa necesita.
    """
    normal = re.sub(r"[^a-z0-9 ]+", "", _sin_acentos(texto))
    normal = re.sub(r"\s+", " ", normal).strip()
    if any(p in normal for p in _PALABRAS_CANCELAR):
        return "cancelar"
    if any(p in normal for p in _PALABRAS_CAMBIAR):
        return "cambiar"
    if hay_propuesta and normal in ("otra", "otro", "prefiero otra"):
        return "cambiar"
    return None


def _atender_cambio_cancelacion(deps: Dependencias, telefono: str, nombre: str,
                                fecha: str, intencion: str, con_ritmo: bool = True) -> dict:
    """Atiende un cambio o cancelación de cita, de día o de noche.

    - Si solo había una propuesta (todavía no se creó la cita), se
      borra la propuesta y se pregunta por el nuevo día.
    - Si la cita ya está creada (estatus agendado en Clientes), se
      borra el evento de Calendar y se limpia la hoja, y se confirma.
    - Si no hay nada que cambiar, se pregunta qué día le viene bien.
    Nunca se repite la frase de fuera de horario: el cliente ya dijo
    lo que quiere, y eso se respeta.
    """
    propuesta = _CITAS_PENDIENTES.get(telefono)
    _borrar_propuesta(deps, telefono)
    leer_cliente = getattr(deps, "leer_cliente", lambda t: None)
    cliente = leer_cliente(telefono) or {}
    fecha_cita = str(cliente.get("fecha_cita", "") or "").strip()
    agendada = str(cliente.get("estatus", "")).strip().lower() == "agendado" and fecha_cita
    if agendada:
        try:
            fecha_bonita = formatear_cita_bonita(fecha_cita)
        except (ValueError, TypeError):
            fecha_bonita = fecha_cita
        cancelar_cita = getattr(deps, "cancelar_cita", lambda t, f: False)
        cancelar_cliente = getattr(deps, "cancelar_cita_cliente", lambda t: None)
        try:
            cancelar_cita(telefono, fecha_cita)
        except Exception:
            pass
        try:
            cancelar_cliente(telefono)
        except Exception:
            pass
        if intencion == "cancelar":
            mensaje = (
                f"Listo, tu cita del {fecha_bonita} quedó cancelada. "
                f"Si quieres agendar otra, dime qué día te viene bien."
            )
        else:
            mensaje = (
                f"Listo, cancelé tu cita del {fecha_bonita}. "
                f"¿Qué día y hora te vienen mejor para la nueva?"
            )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si",
                                    "cancelar cita" if intencion == "cancelar" else "cambiar cita")
        deps.registrar_cliente(fecha, nombre, telefono,
                               "Canceló su cita" if intencion == "cancelar" else "Quiere cambiar su cita",
                               "", "whatsapp", "en conversacion", "no")
        return {"respondio": True, "handoff": False, "cita_cancelada": True}
    if propuesta is not None or intencion == "cambiar":
        mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar cita")
        return {"respondio": True, "handoff": False, "cita_cancelada": False}
    mensaje = "Claro. No tienes ninguna cita agendada con nosotros. ¿Te ayudo con algo más?"
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cancelar cita")
    return {"respondio": True, "handoff": False, "cita_cancelada": False}


# --- Reglas puras (sin internet, se prueban solas) ---


def puede_responder(
    bot_activo: str,
    ultima_respuesta_humana: str,
    ahora: datetime | None = None,
) -> tuple[bool, str]:
    """¿Puede hablar el robot? Devuelve (sí/no, motivo del silencio).

    - bot_activo en NO → no, "boton apagado".
    - Un humano escribió hace menos de 2 horas → no, "humano activo hace menos de 2 horas".
    - Si no, sí.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if str(bot_activo).strip().upper() != "SI":
        return False, "boton apagado"
    if ultima_respuesta_humana:
        try:
            ultima = datetime.fromisoformat(
                str(ultima_respuesta_humana).strip().replace("Z", "+00:00")
            )
            if ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=timezone.utc)
            if ahora - ultima < PAUSA:
                return False, "humano activo hace menos de 2 horas"
        except ValueError:
            pass  # Fecha mal escrita en Control: no se bloquea por eso.
    return True, ""


def robot_activo_para_cliente(valor: str) -> bool:
    """¿El robot le contesta a este cliente? Solo un NO explícito lo apaga.

    La columna robot_activo de Clientes: "NO" → apagado. En blanco,
    "SI" o cualquier otra cosa → encendido (el robot contesta por
    defecto; nadie se queda sin respuesta por una celda vacía).
    """
    return str(valor or "").strip().upper() not in {"NO", "N", "FALSE", "FALSO"}


def foto_es_oficial(url: str, fotos: list[dict]) -> bool:
    """¿Está esta URL en la lista blanca de Fotos oficiales?"""
    url = (url or "").strip()
    if not url:
        return False
    oficiales = {(f.get("url") or "").strip() for f in fotos}
    return url in oficiales


# --- Horarios del negocio (de la hoja Conocimiento) ---

_DIAS = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}
_DIAS_NOMBRE = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _dias_de_texto(texto: str) -> list[int]:
    """Días que cubre un texto como 'Lunes a viernes' o 'Sábado'."""
    texto = texto.lower()
    encontrados = [(m.start(), _DIAS[m.group(0)]) for m in re.finditer(
        r"lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo", texto)]
    if not encontrados:
        return []
    if len(encontrados) == 1:
        return [encontrados[0][1]]
    inicio, fin = encontrados[0][1], encontrados[-1][1]
    if fin < inicio:  # p. ej. "viernes a lunes": no se complica, se toman los dos
        return [inicio, fin]
    return list(range(inicio, fin + 1))


def _horas_de_texto(texto: str) -> tuple[int, int] | None:
    """Horas de un texto como '09:00 a 18:00'. Devuelve (apertura, cierre) en minutos."""
    match = re.search(r"(\d{1,2}):(\d{2})\s*(?:a|-)\s*(\d{1,2}):(\d{2})", texto or "")
    if not match:
        return None
    h1, m1, h2, m2 = (int(x) for x in match.groups())
    return h1 * 60 + m1, h2 * 60 + m2


def horarios_por_dia(conocimiento: list[dict]) -> dict[int, tuple[int, int]]:
    """De Conocimiento (filas tipo=horario) a {día_semana: (apertura, cierre)}."""
    horarios: dict[int, tuple[int, int]] = {}
    for fila in conocimiento:
        if str(fila.get("tipo", "")).strip().lower() != "horario":
            continue
        horas = _horas_de_texto(str(fila.get("respuesta_o_precio", "")))
        if not horas:
            continue
        for dia in _dias_de_texto(str(fila.get("pregunta_o_servicio", ""))):
            horarios[dia] = horas
    return horarios


def _a_hora_local(ahora: datetime) -> datetime:
    """Pasa una fecha a la zona horaria del negocio.

    Ojo: una fecha SIN zona (como "2026-11-14T10:00:00", que es como
    Gemini y el negocio escriben las citas) ya está en hora del
    negocio, no en UTC. Solo las fechas que sí traen zona se convierten.
    """
    zona = ZoneInfo(settings.timezone)
    if ahora.tzinfo is None:
        return ahora.replace(tzinfo=zona)
    return ahora.astimezone(zona)


def horario_abierto(conocimiento: list[dict], ahora: datetime | None = None) -> tuple[bool, str]:
    """¿Está abierto el negocio ahora? Devuelve (sí/no, resumen de horarios).

    Si la hoja no tiene filas de horario, se asume abierto (no se
    bloquea al cliente por falta de datos).
    """
    horarios = horarios_por_dia(conocimiento)
    if not horarios:
        return True, ""
    local = _a_hora_local(ahora or datetime.now(timezone.utc))
    horas = horarios.get(local.weekday())
    if horas is None:
        return False, _resumen_horarios(conocimiento)
    minutos = local.hour * 60 + local.minute
    return horas[0] <= minutos < horas[1], _resumen_horarios(conocimiento)


def _resumen_horarios(conocimiento: list[dict]) -> str:
    """Texto corto con los horarios, p. ej. 'lunes a viernes de 09:00 a 18:00'."""
    partes = []
    for fila in conocimiento:
        if str(fila.get("tipo", "")).strip().lower() != "horario":
            continue
        dia = str(fila.get("pregunta_o_servicio", "")).strip()
        hora = str(fila.get("respuesta_o_precio", "")).strip()
        if dia and hora:
            partes.append(f"{dia.lower()} de {hora}")
    return ", ".join(partes) or "en su horario habitual"


def proxima_apertura(conocimiento: list[dict], ahora: datetime | None = None) -> datetime | None:
    """La próxima fecha en que el negocio abre (fecha con hora de apertura)."""
    horarios = horarios_por_dia(conocimiento)
    if not horarios:
        return None
    local = _a_hora_local(ahora or datetime.now(timezone.utc))
    for adelanto in range(0, 8):
        dia = local + timedelta(days=adelanto)
        horas = horarios.get(dia.weekday())
        if horas is None:
            continue
        apertura = dia.replace(hour=horas[0] // 60, minute=horas[0] % 60, second=0, microsecond=0)
        if adelanto == 0 and local.hour * 60 + local.minute >= horas[0]:
            continue  # hoy ya cerró: buscar el siguiente día
        return apertura
    return None


def formatear_cita_bonita(fecha_iso: str) -> str:
    """'2026-11-14T10:00:00' → 'sábado 14 de noviembre a las 10:00'.

    Sin depender del idioma del servidor: los nombres están escritos
    a mano, en español.
    """
    texto = str(fecha_iso).strip().replace("Z", "+00:00")
    fecha = datetime.fromisoformat(texto)
    local = _a_hora_local(fecha)
    return (
        f"{_DIAS_NOMBRE[local.weekday()]} {local.day} de "
        f"{_MESES[local.month - 1]} a las {local:%H:%M}"
    )


def contar_semana(
    conversaciones: list[dict], clientes: list[dict], desde: datetime, hasta: datetime
) -> dict:
    """Cuenta la última semana. Los números salen de las hojas, no se inventan.

    Devuelve: mensajes_atendidos, clientes_calificados, citas_agendadas,
    handoffs, sin_respuesta_por_humano, motivos_top (lista de (motivo, veces)).
    """
    def en_semana(fila: dict) -> bool:
        try:
            fecha = datetime.fromisoformat(
                str(fila.get("fecha", "")).replace("Z", "+00:00")
            )
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            return desde <= fecha < hasta
        except ValueError:
            return False

    conv = [f for f in conversaciones if en_semana(f)]
    cli = [f for f in clientes if en_semana(f)]
    motivos: dict[str, int] = {}
    for fila in conv:
        motivo = str(fila.get("motivo") or "").strip()
        if motivo:
            motivos[motivo] = motivos.get(motivo, 0) + 1
    return {
        "mensajes_atendidos": sum(
            1 for f in conv if f.get("quien_hablo") == "robot" and f.get("robot_respondio") == "si"
        ),
        # Clientes distintos (por teléfono), no filas: antes, un cliente
        # con 5 mensajes contaba como 5 clientes calificados.
        "clientes_calificados": len({str(f.get("telefono", "")).strip() for f in cli if str(f.get("telefono", "")).strip()}),
        "citas_agendadas": sum(
            1 for f in cli if str(f.get("estatus", "")).strip() == "agendado"
        ),
        "handoffs": sum(
            1 for f in cli if str(f.get("handoff", "")).strip().lower() == "si"
        ),
        "sin_respuesta_por_humano": sum(
            1
            for f in conv
            if f.get("robot_respondio") == "no"
            and "humano activo" in str(f.get("motivo") or "")
        ),
        "motivos_top": sorted(motivos.items(), key=lambda x: -x[1])[:5],
    }


# --- El flujo completo ---


class Dependencias:
    """Los servicios que el robot necesita. Cada método es una sola acción.

    En producción se usan las funciones reales de sheets/whatsapp/etc.
    En las pruebas se reemplazan por falsas. Si un día cambias de
    proveedor (otro Sheets, otro WhatsApp), solo cambia este archivo.
    Los métodos nuevos de la v2 tienen una versión vacía aquí: si una
    dependencia vieja no los tiene, el robot sigue funcionando.
    """

    # Sheets
    def leer_control(self) -> dict: ...
    def leer_robot_activo(self, telefono: str) -> str:
        """Interruptor por cliente (columna robot_activo de Clientes). Por defecto: SI."""
        return "SI"
    def leer_cliente(self, telefono: str) -> dict | None:
        """La fila de Clientes de un teléfono, o None si no está registrado."""
        return None
    def cancelar_cita_cliente(self, telefono: str) -> None:
        """Limpia la cita de un cliente en Clientes (fecha vacía, estatus en conversacion)."""
        ...
    def guardar_propuesta(self, telefono: str, propuesta: dict) -> None:
        """Guarda una propuesta de cita en la hoja (respaldo ante reinicios)."""
        ...
    def borrar_propuesta(self, telefono: str) -> None:
        """Borra una propuesta de cita de la hoja."""
        ...
    def leer_propuestas(self) -> list[dict]:
        """Todas las propuestas guardadas en la hoja (para recuperarlas al arrancar)."""
        return []
    def leer_conocimiento(self) -> list[dict]: ...
    def leer_fotos(self) -> list[dict]: ...
    def leer_historial(self, telefono: str) -> list[dict]: ...
    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""): ...
    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp", estatus="en conversacion", handoff="no"): ...

    # Agente
    def preguntar_agente(self, mensaje, conocimiento, fotos, historial) -> RespuestaAgente:
        return preguntar_agente(mensaje, conocimiento, fotos, historial)

    # WhatsApp / Calendar / correo
    def enviar_texto(self, telefono, texto): ...
    def enviar_foto(self, telefono, url): ...
    def crear_cita(self, nombre, telefono, motivo, fecha_cita) -> dict: ...
    def cancelar_cita(self, telefono, fecha_cita) -> bool:
        """Borra del Calendar la cita de ese teléfono en esa fecha. True si la borró."""
        return False
    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha): ...

    # --- Nuevos en la v2 (vacío = no hacer nada, el robot sigue) ---
    def marcar_leido_y_escribiendo(self, message_id): ...
    def enviar_botones(self, telefono, texto, botones): ...
    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha): ...
    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        """Escribe en la pestaña Diagnóstico (v2.7). Por defecto: nada."""
        ...


def _avisar_por_correo(avisar, *args) -> None:
    """Avisa por correo sin romper nada: best-effort.

    El correo es un aviso al dueño, no parte de la respuesta al
    cliente. Si Gmail no está configurado (o falla la red, o la
    contraseña de aplicación), enviar_correo lanza CorreoError; aquí
    se atrapa, se deja en el registro del servidor y el robot sigue
    con lo suyo: contestar por WhatsApp y registrar en Sheets.
    """
    try:
        avisar(*args)
    except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
        log_aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")


def _diagnostico(deps: Dependencias, fecha, componente: str, estado: str,
                 detalle: str, telefono: str = "", contexto: str = "") -> None:
    """Escribe en la pestaña Diagnóstico, sin romper nada (v2.7).

    Es lo que permite revisar la salud del robot desde la hoja, sin
    entrar a Render: si Gemini falla, si el token muere, si la
    autoprueba sale mal, queda escrito aquí con fecha y detalle.
    """
    try:
        registrar = getattr(deps, "registrar_diagnostico", None)
        if registrar is not None:
            registrar(fecha, componente, estado, detalle, telefono, contexto)
    except Exception as exc:  # noqa: BLE001 - el diagnóstico nunca rompe nada
        log_aviso(f"[diagnostico] No pude escribir en la hoja: {exc}")


def _refrescar_escribiendo(deps: Dependencias, message_id: str, parar: threading.Event) -> None:
    """Hilo que vuelve a prender la burbuja cada 20 segundos.

    La burbuja dura máximo 25 s: si Gemini tarda más, el cliente la
    vería apagarse. Este hilo la refresca hasta que el agente termina.
    Si la llamada falla, no pasa nada: nunca bloquea la respuesta.
    """
    while not parar.wait(20):
        try:
            deps.marcar_leido_y_escribiendo(message_id)
        except Exception:
            pass  # Lo mejor posible: si falla, la respuesta sigue igual.


def atender_mensaje(
    deps: Dependencias,
    telefono: str,
    nombre: str,
    texto: str,
    fecha_iso: str | None = None,
    message_id: str = "",
    con_ritmo: bool = True,
    ahora: datetime | None = None,
) -> dict:
    """Atiende UN mensaje (o un lote ya juntado) de un cliente.

    `texto` puede ser varios mensajes juntos, unidos con saltos de
    línea: el Agrupador ya los juntó. `message_id` es el wamid del
    primer mensaje, para el visto y la burbuja. `con_ritmo=False`
    apaga las pausas (solo para las pruebas, que si no tardarían).
    `ahora` es la hora actual (solo para las pruebas de horario).
    Devuelve un resumen de lo que pasó.
    """
    ahora = ahora or datetime.now(timezone.utc)
    fecha = fecha_iso or ahora.isoformat()
    # 1. ¿Puede responder el robot? Tres frenos, en orden:
    #    (a) botón global (Control), (b) pausa de 2 h si habló un humano,
    #    (c) interruptor por cliente (robot_activo en Clientes, v2.3).
    control = deps.leer_control()
    puede, motivo_silencio = puede_responder(
        control.get("bot_activo", "SI"),
        control.get("ultima_respuesta_humana", ""),
        ahora,
    )
    if puede:
        leer_activo = getattr(deps, "leer_robot_activo", lambda t: "SI")
        if not robot_activo_para_cliente(leer_activo(telefono)):
            puede, motivo_silencio = False, "robot apagado para este cliente"
    # 2. Registrar que llegó el mensaje del cliente (una sola vez, siempre).
    deps.registrar_conversacion(
        fecha, telefono, "cliente", texto,
        "si" if puede else "no", motivo_silencio,
    )
    if not puede:
        # En silencio: sin visto, sin burbuja, sin respuesta. Solo registro.
        return {"respondio": False, "motivo": motivo_silencio, "handoff": False}

    # 3. Visto + "escribiendo...": el cliente ve que lo leyeron.
    # Best-effort: si Meta falla, se sigue igual, sin avisarle al cliente.
    try:
        deps.marcar_leido_y_escribiendo(message_id)
    except Exception:
        pass

    # 3b. "Sí" a una cita propuesta: se confirma por texto, sin botones
    # y sin llamar al agente. Vale de noche (fuera de horario) y de día:
    # si el cliente ya aceptó la fecha, no hay nada que preguntarle.
    # Si la propuesta es vieja (más de 48 h), se descarta y se sigue normal.
    # (v2.7) PERO: un "sí" solo confirma si el último mensaje del robot
    # fue la propuesta. Si lo último que el robot dijo fue "dame un
    # momento" (Gemini falló), un "sí gracias" es cortesía, no una
    # confirmación: el 12 de noviembre de 2026 un "sí gracias" confirmó
    # una cita que ya estaba ocupada y el robot contestó "esa hora ya
    # se ocupó". En ese caso el "sí" va al agente, que atiende normal.
    historial = deps.leer_historial(telefono)
    ultimo_robot = None
    for fila in reversed(historial or []):
        if fila.get("quien_hablo") == "robot":
            ultimo_robot = fila
            break
    ultimo_fue_fallo = bool(
        ultimo_robot
        and (
            ultimo_robot.get("motivo") == "falla tecnica"
            or str(ultimo_robot.get("mensaje", "")).startswith("Dame un momento")
        )
    )
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if propuesta and _es_afirmacion(texto) and not ultimo_fue_fallo:
        creado_en = propuesta.get("creado_en")
        vigente = True
        if creado_en:
            try:
                creado = datetime.fromisoformat(str(creado_en).replace("Z", "+00:00"))
                if creado.tzinfo is None:
                    creado = creado.replace(tzinfo=timezone.utc)
                vigente = ahora - creado < _VIGENCIA_PROPUESTA
            except ValueError:
                vigente = True
        if vigente:
            return _confirmar_cita_propuesta(deps, telefono, nombre, fecha, con_ritmo)
        _borrar_propuesta(deps, telefono)

    # 3c. Cambiar / cancelar cita: se atiende ANTES que el agente, de
    # día y de noche. Un "mejor no" o un "prefiero otra" no es una
    # pregunta nueva: es una decisión sobre la cita que ya tiene.
    intencion = _intencion_cambio(texto, hay_propuesta=telefono in _CITAS_PENDIENTES)
    if intencion is not None:
        return _atender_cambio_cancelacion(deps, telefono, nombre, fecha, intencion, con_ritmo)

    # 4. Cargar lo que el robot necesita saber.
    # (El historial ya se cargó arriba, en el paso 3b, para saber si
    # el último mensaje del robot fue un fallo.)
    conocimiento = deps.leer_conocimiento()
    fotos = deps.leer_fotos()

    # 5. Contexto para el agente (v2.6): la IA contesta SIEMPRE, de día
    # y de noche, y siempre sabe qué hora es, si el negocio está
    # abierto, a qué hora abre, cuál es la próxima apertura y cómo se
    # llama el cliente. Ya NO hay atajo con frase grabada: ni para un
    # primer "hola" de noche, ni como respaldo si Gemini falla.
    # La frase grabada escondía los fallos de Gemini: el cliente veía
    # siempre la misma respuesta y parecía que no había IA, cuando lo
    # que pasaba es que la IA no estaba contestando. Ahora, si Gemini
    # falla, el cliente recibe un "dame un momento" honesto (paso 8)
    # y el dueño un correo: el fallo se ve, no se disfraza.
    abierto, resumen_horarios = horario_abierto(conocimiento, ahora)
    proxima = proxima_apertura(conocimiento, ahora) if not abierto else None
    local_ahora = _a_hora_local(ahora)
    # (v3.1) Mañana, escrito tal cual: el 12 de noviembre el robot
    # ofreció "mañana viernes" a las 00:00 del viernes, cuando hoy YA
    # era viernes. Con el día de mañana explícito en el contexto, el
    # modelo no tiene que calcularlo (y el revisor R4 lo corrige si
    # aun así se equivoca).
    manana = local_ahora + timedelta(days=1)
    contexto = [
        f"Hoy es {_DIAS_NOMBRE[local_ahora.weekday()]} {local_ahora.day} de "
        f"{_MESES[local_ahora.month - 1]}, son las {local_ahora:%H:%M} (hora del negocio).",
        f"Mañana es {_DIAS_NOMBRE[manana.weekday()]} {manana.day} de {_MESES[manana.month - 1]}.",
        f"El negocio está {'ABIERTO' if abierto else 'CERRADO'}: abre {resumen_horarios}.",
    ]
    if nombre:
        contexto.append(f"El cliente se llama {nombre}: salúdalo por su nombre la primera vez.")
    if not abierto:
        proxima_txt = formatear_cita_bonita(proxima.isoformat()) if proxima is not None else ""
        contexto.append(
            "No agendes para hoy ni para una hora en que esté cerrado. "
            f"Si el cliente quiere una cita, ofrécele la próxima apertura: {proxima_txt}."
        )
    propuesta_activa = _CITAS_PENDIENTES.get(telefono)
    if propuesta_activa:
        contexto.append(
            "Ya le propusiste una cita para el "
            f"{propuesta_activa.get('fecha_bonita', '')}: si te pregunta por ella, "
            "recuérdale esa fecha; si dice que le va, confirma; si prefiere otra, pregunta cuál."
        )
    contexto.append("Responde su mensaje con calma, como una persona, usando tu criterio.")
    # (v2.13) Estado del cliente, calculado por código: la IA ya no
    # tiene que deducir en qué va la conversación leyendo las filas
    # crudas de la hoja. Se lo pasamos como datos, no como prosa.
    leer_cliente_fn = getattr(deps, "leer_cliente", lambda t: None)
    try:
        fila_cliente = leer_cliente_fn(telefono) or {}
    except Exception:
        fila_cliente = {}
    estado = estado_cliente(
        historial, _CITAS_PENDIENTES.get(telefono), fila_cliente, nombre
    )
    mensaje_agente = (
        "[Contexto: " + " ".join(contexto) + "]\n"
        "[Estado del cliente: " + json.dumps(estado, ensure_ascii=False) + "]\n"
        f"{texto}"
    )

    # 6. El agente decide qué responder y qué hacer. Mientras piensa,
    # la burbuja se refresca cada 20 segundos.
    parar = threading.Event()
    refresco = threading.Thread(
        target=_refrescar_escribiendo, args=(deps, message_id, parar), daemon=True
    )
    if message_id:
        refresco.start()
    try:
        respuesta = deps.preguntar_agente(mensaje_agente, conocimiento, fotos, historial)
    finally:
        parar.set()

    # (v2.13) Revisor: segunda mirada antes de mandar. Si la respuesta
    # repite una oferta pendiente, ofrece cita en un saludo o dice
    # "ya cerramos", se corrige aquí, no en el teléfono del cliente.
    # La falla técnica ("dame un momento") no se toca: es honesta.
    # Lo corregido queda en Diagnóstico, para ver qué se atrapó.
    if not respuesta.falla_tecnica:
        texto_revisado, violaciones = revisar_respuesta(
            respuesta.respuesta_texto, estado, nombre,
            ahora=local_ahora, telefono=telefono,
        )
        if violaciones:
            _diagnostico(
                deps, fecha, "revision", "CORREGIDO",
                "Reglas corregidas antes de mandar: " + ", ".join(violaciones)
                + f" (modelo: {getattr(respuesta, 'modelo', '') or 'sin dato'})",
                telefono, texto,
            )
            respuesta.respuesta_texto = texto_revisado

    # 7. Foto: solo si está en la lista blanca. Si no, se borra sin avisar al cliente.
    foto = respuesta.foto_oficial_url_or_null
    if not foto_es_oficial(foto, fotos):
        foto = ""

    # 8. Handoff: el robot deja de contestar este hilo.
    if respuesta.necesita_handoff == "si":
        if respuesta.falla_tecnica:
            # Gemini falló: al cliente un "dame un momento" (no silencio),
            # al dueño un correo de error, y queda escrito en Diagnóstico
            # para revisarlo desde la hoja sin entrar a Render (v2.7).
            enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto, dormir=con_ritmo)
            deps.registrar_conversacion(fecha, telefono, "robot", respuesta.respuesta_texto, "si", "falla tecnica")
            _diagnostico(deps, fecha, "gemini", "FALLO", respuesta.motivo_handoff or "Gemini no contestó",
                         telefono, texto)
            _avisar_por_correo(deps.alerta_error, respuesta.motivo_handoff, telefono, texto, fecha)
        else:
            _avisar_por_correo(
                deps.alerta_handoff,
                respuesta.nombre or nombre, telefono, respuesta.motivo_handoff, texto, fecha,
            )
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, "", "whatsapp", "en conversacion", "si",
        )
        return {"respondio": respuesta.falla_tecnica, "motivo": "handoff",
                "handoff": True, "falla_tecnica": respuesta.falla_tecnica}

    # 9. Agendar: NO se crea la cita todavía. Se propone con botones y
    # el cliente confirma. Así no se agenda nada por un malentendido.
    # (v2.4) La fecha que propone el agente se valida: si cae fuera de
    # horario o en el pasado (p. ej. de noche propuso para hoy), se
    # corrige sola a la próxima apertura. Si no hay próxima apertura,
    # no se propone nada: se contesta el texto del agente, sin botones.
    if respuesta.quiere_agendar == "si" and respuesta.fecha_cita:
        try:
            fecha_dt = datetime.fromisoformat(str(respuesta.fecha_cita).replace("Z", "+00:00"))
            local_dt = _a_hora_local(fecha_dt)
            horarios = horarios_por_dia(conocimiento)
            if not horarios:
                # Sin filas de horario en la hoja, no hay contra qué
                # validar: se confía en el agente (como siempre).
                valida = local_dt > _a_hora_local(ahora)
            else:
                horas = horarios.get(local_dt.weekday())
                valida = (
                    horas is not None
                    and horas[0] <= local_dt.hour * 60 + local_dt.minute < horas[1]
                    and local_dt > _a_hora_local(ahora)
                )
        except (ValueError, TypeError):
            valida = False
        if not valida:
            proxima_valida = proxima_apertura(conocimiento, ahora)
            if proxima_valida is not None:
                respuesta.fecha_cita = proxima_valida.isoformat()
            else:
                respuesta.quiere_agendar = "no"
    if respuesta.quiere_agendar == "si" and respuesta.fecha_cita:
        try:
            fecha_bonita = formatear_cita_bonita(respuesta.fecha_cita)
        except (ValueError, TypeError):
            fecha_bonita = respuesta.fecha_cita
        propuesta = (
            f"{respuesta.respuesta_texto}\n\n"
            f"¿Confirmo tu cita para el {fecha_bonita}?"
        )
        _guardar_propuesta(deps, telefono, {
            "nombre": respuesta.nombre or nombre,
            "motivo": respuesta.motivo or texto,
            "fecha_cita": respuesta.fecha_cita,
            "fecha_bonita": fecha_bonita,
            "creado_en": ahora.isoformat(),
        })
        try:
            deps.enviar_botones(telefono, propuesta, BOTONES_CITA)
        except Exception:
            # Si los botones fallan, se manda el texto normal: el cliente
            # puede contestar "sí" escribiendo. Nunca se queda sin respuesta.
            enviar_con_ritmo(deps.enviar_texto, telefono, propuesta, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", propuesta, "si", respuesta.motivo)
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, respuesta.fecha_cita,
            "whatsapp", "en conversacion", "no",
        )
        return {"respondio": True, "handoff": False, "cita_propuesta": True,
                "fecha_cita": respuesta.fecha_cita}

    # 10. Responder por WhatsApp, con ritmo humano: foto oficial primero
    # (si la hay), luego el texto, partido si es largo.
    if foto:
        deps.enviar_foto(telefono, foto)
    enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto, dormir=con_ritmo)

    # 11. Registrar la respuesta del robot y al cliente (las DOS hojas).
    deps.registrar_conversacion(
        fecha, telefono, "robot", respuesta.respuesta_texto, "si",
        respuesta.motivo,
    )
    # (v2.5) De noche, TODO el que escribe es un lead: si el agente no
    # sacó nombre ni motivo (p. ej. solo saludó o preguntó algo corto),
    # se registra igual con su mensaje como motivo. De día se mantiene
    # la regla de siempre (solo si hay nombre o motivo), para no llenar
    # Clientes de saludos. registrar_cliente fusiona por teléfono:
    # nunca duplica la fila.
    if respuesta.nombre or respuesta.motivo or not abierto:
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, respuesta.fecha_cita or "",
            "whatsapp",
            "calificado" if (respuesta.nombre or respuesta.motivo) else "en conversacion",
            "no",
        )
    return {"respondio": True, "handoff": False, "cita": None, "foto": bool(foto)}


def atender_boton(
    deps: Dependencias,
    telefono: str,
    nombre: str,
    boton_id: str,
    fecha_iso: str | None = None,
    con_ritmo: bool = True,
    ahora: datetime | None = None,
) -> dict:
    """Atiende lo que el cliente tocó en los botones de la cita.

    - confirmar_cita: crea la cita y manda la confirmación bonita.
    - cambiar_hora: borra la propuesta y pregunta por otro día y hora.
    - hablar_persona: handoff (texto corto al cliente + correo al dueño).
    """
    ahora = ahora or datetime.now(timezone.utc)
    fecha = fecha_iso or ahora.isoformat()

    # Interruptor por cliente (v2.3): si el robot está apagado para este
    # cliente, no crea citas ni contesta. La propuesta pendiente se
    # borra para que un "sí" viejo no la confirme después. Excepción:
    # "hablar con una persona" sigue funcionando: es el camino al
    # humano, no una respuesta del robot.
    if boton_id in ("confirmar_cita", "cambiar_hora"):
        leer_activo = getattr(deps, "leer_robot_activo", lambda t: "SI")
        if not robot_activo_para_cliente(leer_activo(telefono)):
            _borrar_propuesta(deps, telefono)
            deps.registrar_conversacion(
                fecha, telefono, "cliente", f"(botón {boton_id})", "no",
                "robot apagado para este cliente",
            )
            return {"respondio": False, "motivo": "robot apagado para este cliente", "handoff": False}

    if boton_id == "confirmar_cita":
        # El mismo camino que el "sí" por texto (ver _confirmar_cita_propuesta).
        return _confirmar_cita_propuesta(deps, telefono, nombre, fecha, con_ritmo)

    if boton_id == "cambiar_hora":
        _borrar_propuesta(deps, telefono)
        mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar hora")
        return {"respondio": True, "handoff": False}

    if boton_id == "hablar_persona":
        propuesta = _CITAS_PENDIENTES.get(telefono)
        _borrar_propuesta(deps, telefono)
        motivo = (propuesta or {}).get("motivo", "El cliente pidió hablar con una persona")
        mensaje = "Claro, te paso con una persona del negocio. Te atienden en un momento."
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        _avisar_por_correo(deps.alerta_handoff, nombre, telefono, motivo, mensaje, fecha)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", motivo)
        deps.registrar_cliente(
            fecha, nombre, telefono, motivo, "", "whatsapp", "en conversacion", "si",
        )
        return {"respondio": True, "motivo": "handoff", "handoff": True}

    # Botón desconocido: se trata como mensaje normal, con calma.
    mensaje = "Claro. ¿Me cuentas qué necesitas?"
    enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
    return {"respondio": True, "motivo": "boton desconocido", "handoff": False}
