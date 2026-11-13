"""Punto de entrada del robot. Se arranca con:  uvicorn app:app --port 8000

Endpoints:
- GET  /health .......... ¿está vivo el robot? (para Render/Railway y para ti)
- GET  /webhook ......... verificación de Meta (te pide el VERIFY_TOKEN)
- POST /webhook ......... llegan los mensajes de WhatsApp
- POST /pausa ........... marca que una persona atendió un chat (arranca la pausa de 2 h)
- POST /reporte-semanal . manda el reporte ahora, sin esperar al lunes

Versión 2: el webhook NO espera a Gemini. Solo mete el mensaje en el
Agrupador (robot/agrupar.py) y devuelve 200 enseguida. El Agrupador
espera 7 segundos después del último mensaje, junta todo lo que mandó
el cliente y lo procesa una sola vez, en segundo plano. Los botones
(confirmar / cambiar hora / hablar con persona) se atienden aparte,
en cuanto llegan, porque son una decisión, no un mensaje para juntar.

El reporte semanal también corre solo, cada lunes a las 08:00 (hora del
negocio), con APScheduler. El webhook de WhatsApp apunta a la URL pública
de este servidor (ver README, despliegue).

NO hay recordatorios por WhatsApp en este robot, por decisión de Jose:
ni un día antes, ni una hora antes, ni ningún trabajo programado que
mande WhatsApp. El único trabajo programado es el reporte por correo.

Versión 2.1: las alertas por correo son best-effort. Si Gmail no está
configurado, el correo falla en silencio (queda en el registro) y el
cliente recibe igual su respuesta de WhatsApp, sin duplicados.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

from robot import booking, gemini, mail, sheets, whatsapp
from robot.agent import preguntar_agente
from robot.agrupar import Agrupador
from robot.config import settings
from robot.logic import Dependencias, atender_boton, atender_mensaje
from robot.report import generar_reporte_semanal

app = FastAPI(title="Robot WhatsApp — IA gratis", version="2.5.0")


# --- Las dependencias reales: conectan la lógica con Google, Gemini y WhatsApp ---


class DependenciasReales(Dependencias):
    """Une logic.atender_mensaje con los servicios de verdad."""

    def leer_control(self):
        return sheets.leer_control()

    def leer_robot_activo(self, telefono):
        return sheets.leer_robot_activo(telefono)

    def leer_cliente(self, telefono):
        return sheets.leer_cliente(telefono)

    def cancelar_cita_cliente(self, telefono):
        sheets.cancelar_cita_cliente(telefono)

    def leer_conocimiento(self):
        return sheets.leer_conocimiento()

    def leer_fotos(self):
        return sheets.leer_fotos_oficiales()

    def leer_historial(self, telefono):
        return sheets.leer_historial(telefono)

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        sheets.registrar_conversacion(fecha, telefono, quien, mensaje, respondio, motivo)

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp", estatus="en conversacion", handoff="no"):
        sheets.registrar_cliente(fecha, nombre, telefono, motivo, fecha_cita, origen, estatus, handoff)

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        return preguntar_agente(mensaje, conocimiento, fotos, historial)

    def enviar_texto(self, telefono, texto):
        whatsapp.enviar_texto(telefono, texto)

    def enviar_foto(self, telefono, url):
        whatsapp.enviar_foto(telefono, url)

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        return booking.crear_cita(nombre, telefono, motivo, fecha_cita)

    def cancelar_cita(self, telefono, fecha_cita):
        return booking.cancelar_cita(telefono, fecha_cita)

    def guardar_propuesta(self, telefono, propuesta):
        sheets.guardar_propuesta(telefono, propuesta)

    def borrar_propuesta(self, telefono):
        sheets.borrar_propuesta(telefono)

    def leer_propuestas(self):
        return sheets.leer_propuestas()

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        # Best-effort también aquí (doble protección, ver logic.py):
        # si Gmail no está configurado, el correo no debe romper nada.
        try:
            mail.alerta_handoff(nombre, telefono, motivo, ultimo_mensaje, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            print(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    # --- Nuevos en la v2 ---
    def marcar_leido_y_escribiendo(self, message_id):
        whatsapp.marcar_leido_y_escribiendo(message_id)

    def enviar_botones(self, telefono, texto, botones):
        whatsapp.enviar_botones(telefono, texto, botones)

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        try:
            mail.alerta_error(motivo, telefono, ultimo_mensaje, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            print(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")


_DEPS = DependenciasReales()


def _procesar_lote(telefono: str, nombre: str, textos: list[str], wamids: list[str]) -> None:
    """El Agrupador juntó los mensajes de un cliente: atenderlos de una vez.

    Corre en segundo plano. Si algo inesperado falla (Sheets caído, red),
    el cliente NO se queda en silencio: recibe un "dame un momento" y el
    dueño un correo. Eso es lo último que se intenta; si hasta eso falla,
    queda en el registro del servidor.
    """
    texto_unido = "\n".join(textos)
    primer_wamid = wamids[0] if wamids else ""
    try:
        atender_mensaje(_DEPS, telefono, nombre, texto_unido, message_id=primer_wamid)
    except Exception as exc:  # noqa: BLE001 - nunca dejar al cliente sin respuesta
        print(f"[lote] Error atendiendo a {telefono}: {exc}")
        # (v2.5) El fallo queda VISIBLE en la hoja, no solo en el registro
        # del servidor: si el token de WhatsApp murió a las 3 am, el dueño
        # lo ve en Conversaciones en la mañana, aunque el correo falle.
        # Un 401 es casi siempre "token vencido o inválido".
        motivo_fallo = (
            "token de WhatsApp inválido o vencido (401)"
            if "401" in str(exc) else "error whatsapp"
        )
        try:
            sheets.registrar_conversacion(
                datetime.now(timezone.utc).isoformat(), telefono, "robot",
                "(no se pudo enviar la respuesta por WhatsApp: revisa el token)",
                "no", motivo_fallo,
            )
        except Exception as exc4:  # noqa: BLE001 - la hoja también puede fallar
            print(f"[lote] Tampoco pude registrar el fallo en la hoja: {exc4}")
        # El aviso por WhatsApp y el aviso por correo van separados:
        # si el correo falla (p. ej. Gmail sin configurar), el cliente
        # igual recibe su "dame un momento" y no hay duplicados.
        try:
            whatsapp.enviar_texto(
                telefono,
                "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
            )
        except Exception as exc2:  # noqa: BLE001
            print(f"[lote] Tampoco pude avisar por WhatsApp a {telefono}: {exc2}")
        try:
            mail.alerta_error(f"Error inesperado: {exc}", telefono, texto_unido,
                              datetime.now(timezone.utc).isoformat())
        except Exception as exc3:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            print(f"[correo] No se pudo avisar por correo (el robot sigue): {exc3}")


# Un solo Agrupador para todo el servidor: un buzón por teléfono.
_AGRUPADOR = Agrupador(_procesar_lote, espera_segundos=settings.espera_agrupar_segundos)


def _ingresar_mensaje(mensaje: dict, valor: dict) -> None:
    """Mete UN mensaje en el buzón (o atiende un botón). Corre en segundo plano.

    - Texto: directo al Agrupador.
    - Audio: primero se descarga y Gemini lo transcribe; el texto que
      sale se mete al Agrupador (así el audio también se junta con los
      textos que lleguen después).
    - Botón: no se agrupa, se atiende en cuanto llega.
    - Imagen, sticker, ubicación: el robot todavía no los atiende.
    """
    telefono = mensaje.get("from", "")
    if not telefono:
        return
    nombre = ""
    for contacto in valor.get("contacts", []):
        if contacto.get("wa_id") == telefono:
            nombre = contacto.get("profile", {}).get("name", "")
    tipo = mensaje.get("type", "")
    wamid = mensaje.get("id", "")
    if tipo == "interactive":
        boton = mensaje.get("interactive", {}).get("button_reply", {})
        boton_id = boton.get("id", "")
        if not boton_id:
            return
        try:
            atender_boton(_DEPS, telefono, nombre, boton_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[boton] Error atendiendo botón {boton_id} de {telefono}: {exc}")
        return
    if tipo == "text":
        texto = mensaje.get("text", {}).get("body", "")
    elif tipo == "audio":
        media_id = mensaje.get("audio", {}).get("id", "")
        try:
            audio_bytes, mime = whatsapp.descargar_audio(media_id)
            texto = gemini.transcribir_audio(audio_bytes, mime)
        except Exception as exc:  # noqa: BLE001
            print(f"[audio] No pude entender el audio de {telefono}: {exc}")
            texto = ""
        if not texto:
            # (v2.5) Un audio que no se entendió NO se ignora en silencio:
            # se le pide al cliente que lo escriba. 24/7 significa que
            # nadie se queda esperando sin saber qué pasó.
            _responder_directo(
                telefono,
                "No pude escuchar tu audio, ¿me lo escribes por favor? Así te atiendo enseguida.",
                "(audio no entendido)",
            )
            return
    elif tipo in ("image", "sticker", "location", "document", "video", "contacts"):
        # (v2.5) Una foto, una ubicación o un sticker tampoco se ignoran
        # en silencio: el robot no puede ver la foto, así que pide que se
        # lo cuenten con palabras. Antes, esto no recibía nada.
        _responder_directo(
            telefono,
            "Gracias, lo recibí. ¿Me cuentas con tus palabras qué necesitas? Así te ayudo mejor.",
            f"({tipo} recibido)",
        )
        return
    else:
        return
    if not texto:
        return
    _AGRUPADOR.agregar(telefono, texto, wamid=wamid, nombre=nombre)


def _responder_directo(telefono: str, texto: str, motivo: str) -> None:
    """Manda un texto corto directo (sin Agrupador ni agente) y lo registra.

    Para los casos que el robot no puede atender con IA (una foto, un
    audio que no se entendió): el cliente recibe algo en vez de silencio.
    Todo con try/except: esto nunca debe tumbar el webhook.
    """
    ahora = datetime.now(timezone.utc).isoformat()
    try:
        sheets.registrar_conversacion(ahora, telefono, "cliente", motivo, "si", "")
    except Exception as exc:  # noqa: BLE001
        print(f"[directo] No pude registrar el mensaje de {telefono}: {exc}")
    try:
        whatsapp.enviar_texto(telefono, texto)
        sheets.registrar_conversacion(ahora, telefono, "robot", texto, "si", motivo)
    except Exception as exc:  # noqa: BLE001
        print(f"[directo] No pude responder a {telefono}: {exc}")
        try:
            sheets.registrar_conversacion(
                ahora, telefono, "robot",
                "(no se pudo enviar la respuesta por WhatsApp: revisa el token)",
                "no", "error whatsapp",
            )
        except Exception:
            pass


# --- Endpoints ---


@app.get("/health")
def health():
    """¿Está vivo? Devuelve ok y la hora. Úsalo para probar que arrancó."""
    return {"ok": True, "hora": datetime.now(timezone.utc).isoformat()}


@app.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
):
    """Meta llama aquí cuando configuras el webhook. Si el token coincide,
    se le devuelve el challenge tal cual. Si no, se rechaza."""
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token incorrecto", status_code=403)


@app.post("/webhook")
async def recibir_whatsapp(request: Request):
    """Llegó algo de WhatsApp. Se devuelve 200 ENSEGUIDA y el trabajo
    pasa a segundo plano (un hilo por mensaje). Así Meta no reintenta
    por tardar, y el cliente no recibe respuestas duplicadas.

    Lo que NO es un mensaje (p. ej. confirmaciones de entrega o de
    lectura que manda Meta) se ignora sin hacer nada.
    """
    datos = await request.json()
    try:
        for entrada in datos.get("entry", []):
            for cambio in entrada.get("changes", []):
                valor = cambio.get("value", {})
                for mensaje in valor.get("messages", []):
                    hilo = threading.Thread(
                        target=_ingresar_mensaje, args=(mensaje, valor), daemon=True
                    )
                    hilo.start()
    except Exception as exc:  # noqa: BLE001 - el webhook nunca debe caerse
        print(f"[webhook] Error leyendo el mensaje: {exc}")
    return {"ok": True}


@app.post("/pausa")
async def marcar_pausa(request: Request):
    """Marca que una persona atendió un chat: arranca la pausa de 2 horas.

    Úsalo cuando tú (o alguien del negocio) le escriba a un cliente por
    WhatsApp. Body: {"telefono": "6671234567"}.
    También puedes escribir la fecha directo en Control!B2 de la hoja.
    """
    datos = await request.json()
    telefono = str(datos.get("telefono", ""))
    ahora = datetime.now(timezone.utc).isoformat()
    sheets.actualizar_ultima_respuesta_humana(ahora)
    # También queda registrado que un humano habló en ese chat.
    sheets.registrar_conversacion(ahora, telefono, "humano", "(la persona atendió el chat)", "no", "humano activo hace menos de 2 horas")
    return {"ok": True, "pausa_hasta": ahora, "telefono": telefono}


@app.post("/reporte-semanal")
def reporte_ahora():
    """Manda el reporte semanal ahora, sin esperar al lunes. Para probarlo."""
    resultado = generar_reporte_semanal()
    return {"ok": True, "semana": resultado["semana"]}


# --- Reporte semanal automático: lunes 08:00 ---
# Es el ÚNICO trabajo programado del robot, y manda correo, nunca WhatsApp.

scheduler = BackgroundScheduler(timezone=settings.timezone)
scheduler.add_job(
    generar_reporte_semanal,
    CronTrigger(day_of_week=settings.reporte_dia_semana, hour=settings.reporte_hora, minute=settings.reporte_minuto),
    id="reporte-semanal",
    replace_existing=True,
)


@app.on_event("startup")
def arrancar():
    """Al arrancar: avisa si faltan claves y prende el programador del lunes."""
    faltantes = __import__("robot.config", fromlist=["faltan_claves"]).faltan_claves()
    if faltantes:
        print(f"[robot] AVISO: faltan en el .env: {', '.join(faltantes)}. Ver README.")
    else:
        print("[robot] Claves listas. Robot arrancado.")
    # (v2.5) Recuperar las propuestas guardadas en la hoja: si Render se
    # reinició, los clientes pueden confirmar igual sus citas pendientes.
    try:
        from robot.logic import cargar_propuestas

        n = cargar_propuestas(_DEPS)
        if n:
            print(f"[robot] Recuperé {n} propuesta(s) de cita de la hoja.")
    except Exception as exc:  # noqa: BLE001 - sin propuestas, el robot sigue igual
        print(f"[robot] No pude recuperar propuestas de la hoja: {exc}")
    scheduler.start()
    print(f"[robot] Reporte semanal programado: lunes {settings.reporte_hora:02d}:{settings.reporte_minuto:02d} ({settings.timezone}).")


@app.on_event("shutdown")
def apagar():
    scheduler.shutdown()
