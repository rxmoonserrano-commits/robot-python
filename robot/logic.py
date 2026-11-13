"""El cerebro del robot: el flujo completo, paso a paso.

Versión 2. Lo que ya hacía la v1 sigue igual (botón de apagado, pausa
de 2 h, lista blanca de fotos, Gemini gratis, agendar, handoff por
correo, registro en las DOS hojas). Lo nuevo de la v2:

1. Visto + "escribiendo...": cuando el robot va a contestar, marca el
   mensaje como leído (palomitas azules) y muestra la burbuja. Si Gemini
   tarda más de ~20 s, se vuelve a prender (un hilo que refresca).
   Nunca en pausa, nunca apagado, nunca en handoff.
2. Esperar y juntar: app.py mete los mensajes en el Agrupador y aquí
   llega UN solo texto con todo junto. Esta función ya no contesta
   mensaje por mensaje.
3. Ritmo humano: antes de contestar espera 1-3 s y, si la respuesta es
   larga, la parte en 2 mensajes cortos (robot/ritmo.py).
4. Botones: cuando el agente propone agendar, NO se crea la cita
   todavía. Se le muestran 3 botones: Confirmar, Cambiar hora, Hablar
   con una persona. La cita se crea solo cuando el cliente toca
   Confirmar (logic.atender_boton). Así no se agenda nada por error.
5. Confirmación bonita: al confirmar, la respuesta trae nombre, día,
   hora y duración, y cómo cambiarla. Es una respuesta inmediata en
   la misma conversación, NO un recordatorio (no hay recordatorios
   por WhatsApp en este robot, por decisión de Jose).
6. Si Gemini falla: el cliente recibe un "dame un momento" y el dueño
   un correo. El robot NUNCA se queda callado por un error.
7. Fuera de horario: si el negocio está cerrado según Conocimiento,
   se le dice a qué hora abre y se le ofrece agendar para el próximo
   día que abre, en vez de agendar una hora imposible.

Versión 2.1: las alertas por correo son best-effort. Si Gmail no está
configurado (falta la contraseña de aplicación), el correo falla, pero
eso NUNCA rompe la respuesta de WhatsApp: se deja en el registro y el
cliente recibe igual su respuesta. Antes, un correo fallido rompía
atender_mensaje y el cliente se quedaba sin respuesta.

Versión 2.2 (pulido, 2026-11-12):
1. Fuera de horario ya no pierde al cliente: se guarda la propuesta
   (próxima apertura) y se registra el lead en Clientes. Si el cliente
   contesta "sí" por texto, la cita se crea de verdad, aunque siga
   siendo de noche. Antes, un "sí" nocturno volvía a ofrecer lo mismo
   en un bucle y nunca se agendaba nada.
2. Clientes sin duplicados: registrar_cliente ya no agrega una fila
   nueva por cada mensaje del mismo teléfono. Si el teléfono ya existe,
   actualiza su fila (ver sheets.fusionar_cliente): un cliente, una
   fila. Eso también arregla los contadores, que contaban filas y no
   clientes distintos.

Para que se pueda probar sin internet, `atender_mensaje` recibe un
objeto `dependencias` con los servicios (Sheets, agente, WhatsApp,
Calendar, correo). En producción son los reales; en las pruebas
(test_simulado.py, test_v2.py) son falsos. La lógica es la misma.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .agent import RespuestaAgente, preguntar_agente
from .config import settings
from .ritmo import enviar_con_ritmo

PAUSA = timedelta(hours=2)

# Botones que se muestran al proponer una cita (id, título).
BOTONES_CITA = [
    ("confirmar_cita", "Confirmar"),
    ("cambiar_hora", "Cambiar hora"),
    ("hablar_persona", "Hablar con persona"),
]

# Citas propuestas esperando que el cliente toque un botón (o diga "sí").
# Vive en memoria: si el servidor se reinicia, la propuesta se pierde
# y el cliente solo tiene que volver a pedir la cita (sin drama).
# Mejora pendiente (no de esta versión): guardarla en la hoja, no en memoria.
_CITAS_PENDIENTES: dict[str, dict] = {}

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
        _CITAS_PENDIENTES.pop(telefono, None)
        mensaje = (
            "Esa hora ya se ocupó, perdón. ¿Qué otro día y hora "
            "te vienen mejor? Te la agendo enseguida."
        )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "hora ocupada")
        return {"respondio": True, "motivo": "hora ocupada", "handoff": False}
    _CITAS_PENDIENTES.pop(telefono, None)
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


def mensaje_fuera_de_horario(conocimiento: list[dict], ahora: datetime | None = None) -> str:
    """Qué decirle al cliente cuando escribe fuera de horario."""
    _, resumen = horario_abierto(conocimiento, ahora)
    proxima = proxima_apertura(conocimiento, ahora)
    if proxima is not None:
        dia_txt = formatear_cita_bonita(proxima.isoformat())
        return (
            f"Hola, gracias por escribir. Ahora estamos cerrados, "
            f"abrimos {resumen}. Te puedo agendar para el {dia_txt}, "
            f"¿te va esa fecha o prefieres otra?"
        )
    return (
        f"Hola, gracias por escribir. Ahora estamos cerrados, "
        f"abrimos {resumen}. ¿Quieres que te agende para cuando abramos?"
    )


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
    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha): ...

    # --- Nuevos en la v2 (vacío = no hacer nada, el robot sigue) ---
    def marcar_leido_y_escribiendo(self, message_id): ...
    def enviar_botones(self, telefono, texto, botones): ...
    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha): ...


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
        print(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")


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
    # 1. ¿Puede responder el robot? (botón de apagado + pausa de 2 h)
    control = deps.leer_control()
    puede, motivo_silencio = puede_responder(
        control.get("bot_activo", "SI"),
        control.get("ultima_respuesta_humana", ""),
        ahora,
    )
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
    propuesta = _CITAS_PENDIENTES.get(telefono)
    if propuesta and _es_afirmacion(texto):
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
        _CITAS_PENDIENTES.pop(telefono, None)

    # 4. Cargar lo que el robot necesita saber.
    conocimiento = deps.leer_conocimiento()
    fotos = deps.leer_fotos()
    historial = deps.leer_historial(telefono)

    # 5. Fuera de horario: no se agenda nada imposible. Se contesta con
    # calma y se ofrece el próximo día que abre. Y, a diferencia de
    # antes, la propuesta SÍ se guarda y el cliente SÍ queda registrado
    # como lead: si contesta "sí", el paso 3b crea la cita.
    abierto, _ = horario_abierto(conocimiento, ahora)
    if not abierto:
        mensaje = mensaje_fuera_de_horario(conocimiento, ahora)
        proxima = proxima_apertura(conocimiento, ahora)
        if proxima is not None:
            _CITAS_PENDIENTES[telefono] = {
                "nombre": nombre,
                "motivo": texto,
                "fecha_cita": proxima.isoformat(),
                "fecha_bonita": formatear_cita_bonita(proxima.isoformat()),
                "creado_en": ahora.isoformat(),
            }
            deps.registrar_cliente(
                fecha, nombre, telefono, texto, proxima.isoformat(),
                "whatsapp", "en conversacion", "no",
            )
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "fuera de horario")
        return {"respondio": True, "fuera_de_horario": True, "handoff": False,
                "cita_propuesta": proxima is not None,
                "fecha_cita": proxima.isoformat() if proxima is not None else ""}

    # 6. El agente decide qué responder y qué hacer. Mientras piensa,
    # la burbuja se refresca cada 20 segundos.
    parar = threading.Event()
    refresco = threading.Thread(
        target=_refrescar_escribiendo, args=(deps, message_id, parar), daemon=True
    )
    if message_id:
        refresco.start()
    try:
        respuesta = deps.preguntar_agente(texto, conocimiento, fotos, historial)
    finally:
        parar.set()

    # 7. Foto: solo si está en la lista blanca. Si no, se borra sin avisar al cliente.
    foto = respuesta.foto_oficial_url_or_null
    if not foto_es_oficial(foto, fotos):
        foto = ""

    # 8. Handoff: el robot deja de contestar este hilo.
    if respuesta.necesita_handoff == "si":
        if respuesta.falla_tecnica:
            # Gemini falló: al cliente un "dame un momento" (no silencio)
            # y al dueño un correo de error. El cliente no se queda esperando.
            enviar_con_ritmo(deps.enviar_texto, telefono, respuesta.respuesta_texto, dormir=con_ritmo)
            deps.registrar_conversacion(fecha, telefono, "robot", respuesta.respuesta_texto, "si", "falla tecnica")
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
    if respuesta.quiere_agendar == "si" and respuesta.fecha_cita:
        try:
            fecha_bonita = formatear_cita_bonita(respuesta.fecha_cita)
        except (ValueError, TypeError):
            fecha_bonita = respuesta.fecha_cita
        propuesta = (
            f"{respuesta.respuesta_texto}\n\n"
            f"¿Confirmo tu cita para el {fecha_bonita}?"
        )
        _CITAS_PENDIENTES[telefono] = {
            "nombre": respuesta.nombre or nombre,
            "motivo": respuesta.motivo or texto,
            "fecha_cita": respuesta.fecha_cita,
            "fecha_bonita": fecha_bonita,
            "creado_en": ahora.isoformat(),
        }
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
    if respuesta.nombre or respuesta.motivo:
        deps.registrar_cliente(
            fecha, respuesta.nombre or nombre, telefono,
            respuesta.motivo or texto, respuesta.fecha_cita or "",
            "whatsapp",
            "calificado",
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

    if boton_id == "confirmar_cita":
        # El mismo camino que el "sí" por texto (ver _confirmar_cita_propuesta).
        return _confirmar_cita_propuesta(deps, telefono, nombre, fecha, con_ritmo)

    if boton_id == "cambiar_hora":
        _CITAS_PENDIENTES.pop(telefono, None)
        mensaje = "Claro, sin problema. ¿Qué día y hora te vienen mejor?"
        enviar_con_ritmo(deps.enviar_texto, telefono, mensaje, dormir=con_ritmo)
        deps.registrar_conversacion(fecha, telefono, "robot", mensaje, "si", "cambiar hora")
        return {"respondio": True, "handoff": False}

    if boton_id == "hablar_persona":
        propuesta = _CITAS_PENDIENTES.pop(telefono, None)
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
