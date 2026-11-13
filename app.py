"""Punto de entrada del robot. Se arranca con:  uvicorn app:app --port 8000

Endpoints:
- GET  /health .......... ¿está vivo el robot? (para Render/Railway y para ti)
- GET  /webhook ......... verificación de Meta (te pide el VERIFY_TOKEN)
- POST /webhook ......... llegan los mensajes de WhatsApp
- POST /pausa ........... marca que una persona atendió un chat (arranca la pausa de 2 h)
- POST /reporte-semanal . manda el reporte ahora, sin esperar al lunes

Versión 2: el webhook NO espera a Gemini. Solo mete el mensaje en el
Agrupador (robot/agrupar.py) y devuelve 200 enseguida. El Agrupador
espera 15 segundos después del último mensaje, junta todo lo que mandó
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

import json
import os
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from robot import booking, gemini, mail, salud, seguridad, sheets, whatsapp
from robot.abuso import Limitador
from robot.agent import preguntar_agente
from robot.agrupar import Agrupador
from robot.config import settings
from robot.logic import Dependencias, atender_boton, atender_mensaje
from robot.registro import aviso, configurar as configurar_registro, error, info
from robot.vigilancia import LOTE_LENTO_SEGUNDOS, con_vigilancia
from robot.report import generar_reporte_semanal, generar_resumen_manana

configurar_registro()

VERSION = "3.3.1"
app = FastAPI(title="Robot WhatsApp — IA gratis", version=VERSION)


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

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        sheets.guardar_memoria_cliente(telefono, resumen, interes,
                                       proxima_accion, preferencias)

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
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    # --- Nuevos en la v3.3 ---
    def proximos_huecos_libres(self, conocimiento, ahora):
        from robot.logic import horarios_por_dia

        return booking.proximos_huecos_libres(horarios_por_dia(conocimiento), ahora)

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        try:
            mail.alerta_cita_confirmada(nombre, telefono, motivo, fecha_bonita, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        try:
            mail.alerta_lead_caliente(nombre, telefono, motivo, ultimo_mensaje, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    # --- Nuevos en la v2 ---
    def marcar_leido_y_escribiendo(self, message_id):
        whatsapp.marcar_leido_y_escribiendo(message_id)

    def enviar_botones(self, telefono, texto, botones):
        whatsapp.enviar_botones(telefono, texto, botones)

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        try:
            mail.alerta_error(motivo, telefono, ultimo_mensaje, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        sheets.registrar_diagnostico(fecha, componente, estado, detalle, telefono, contexto)


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

    def _avisar_lote_lento():
        """El lote lleva más de 90 s: que se vea y que el cliente sepa.

        (v3.1) El 12 de noviembre un lote se quedó más de 45 minutos
        sin responder ni fallar, sin dejar rastro en ningún lado. Con
        vigilancia, a los 90 s queda en Diagnóstico y el cliente
        recibe un "dame un momento"; la respuesta real llega igual
        cuando el trabajo termine.
        """
        try:
            sheets.registrar_diagnostico(
                datetime.now(timezone.utc), "lote", "TARDANDO",
                f"El lote lleva más de {LOTE_LENTO_SEGUNDOS} s procesando; "
                "el cliente recibió un 'dame un momento'.",
                telefono, texto_unido)
        except Exception:
            pass
        try:
            whatsapp.enviar_texto(
                telefono,
                "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
            )
            sheets.registrar_conversacion(
                datetime.now(timezone.utc).isoformat(), telefono, "robot",
                "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
                "si", "lote tardando")
        except Exception as exc2:  # noqa: BLE001 - el aviso nunca rompe el lote
            error(f"[lote] Tampoco pude avisar que el lote tarda a {telefono}: {exc2}")

    try:
        con_vigilancia(
            lambda: atender_mensaje(_DEPS, telefono, nombre, texto_unido, message_id=primer_wamid),
            _avisar_lote_lento,
            segundos=LOTE_LENTO_SEGUNDOS,
        )
    except Exception as exc:  # noqa: BLE001 - nunca dejar al cliente sin respuesta
        error(f"[lote] Error atendiendo a {telefono}: {exc}")
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
            error(f"[lote] Tampoco pude registrar el fallo en la hoja: {exc4}")
        # (v2.7) El fallo también queda en Diagnóstico, con el error exacto.
        sheets.registrar_diagnostico(
            datetime.now(timezone.utc), "whatsapp", "FALLO", str(exc)[:300],
            telefono, texto_unido)
        # El aviso por WhatsApp y el aviso por correo van separados:
        # si el correo falla (p. ej. Gmail sin configurar), el cliente
        # igual recibe su "dame un momento" y no hay duplicados.
        try:
            whatsapp.enviar_texto(
                telefono,
                "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
            )
        except Exception as exc2:  # noqa: BLE001
            error(f"[lote] Tampoco pude avisar por WhatsApp a {telefono}: {exc2}")
        try:
            mail.alerta_error(f"Error inesperado: {exc}", telefono, texto_unido,
                              datetime.now(timezone.utc).isoformat())
        except Exception as exc3:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc3}")


# Un solo Agrupador para todo el servidor: un buzón por teléfono.
# (v3.0) El buzón se guarda en buzon.json: si el servidor se
# reinicia, los lotes pendientes se recuperan al arrancar.
_BUZON_ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buzon.json")
_AGRUPADOR = Agrupador(
    _procesar_lote,
    espera_segundos=settings.espera_agrupar_segundos,
    archivo=_BUZON_ARCHIVO,
)

# (v3.3) Anti-abuso: un solo limitador para todo el servidor. 10
# mensajes en 60 s por teléfono: más que eso es una ráfaga, no una
# conversación, y agota la cuota gratis de Gemini.
_LIMITADOR = Limitador()


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
            error(f"[boton] Error atendiendo botón {boton_id} de {telefono}: {exc}")
        return
    if tipo == "text":
        texto = mensaje.get("text", {}).get("body", "")
    elif tipo == "audio":
        media_id = mensaje.get("audio", {}).get("id", "")
        try:
            audio_bytes, mime = whatsapp.descargar_audio(media_id)
            texto = gemini.transcribir_audio(audio_bytes, mime)
        except Exception as exc:  # noqa: BLE001
            aviso(f"[audio] No pude entender el audio de {telefono}: {exc}")
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
    # (v3.3) Anti-abuso: si un teléfono manda muchos mensajes seguidos,
    # no se procesan todos: se le avisa UNA vez y se ignoran los demás
    # hasta que pase la ventana. Protege la cuota gratis de Gemini.
    decision = _LIMITADOR.registrar(telefono)
    if decision == "avisar":
        _responder_directo(
            telefono,
            "Recibí muchos mensajes seguidos, dame un momento y te atiendo con calma.",
            "(anti-abuso: ráfaga de mensajes)",
        )
        return
    if decision == "silencio":
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
        error(f"[directo] No pude registrar el mensaje de {telefono}: {exc}")
    try:
        whatsapp.enviar_texto(telefono, texto)
        sheets.registrar_conversacion(ahora, telefono, "robot", texto, "si", motivo)
    except Exception as exc:  # noqa: BLE001
        error(f"[directo] No pude responder a {telefono}: {exc}")
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
    """¿Está vivo? Devuelve ok, la versión y la hora. Úsalo para probar que arrancó."""
    return {"ok": True, "version": VERSION, "hora": datetime.now(timezone.utc).isoformat()}


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

    (v3.0) Si META_APP_SECRET está configurado, se verifica la firma
    X-Hub-Signature-256: sin firma válida, 403 sin procesar nada.
    """
    cuerpo = await request.body()
    if not seguridad.verificar_firma_meta(
        cuerpo,
        request.headers.get("X-Hub-Signature-256"),
        settings.meta_app_secret,
    ):
        return PlainTextResponse("Firma inválida", status_code=403)
    datos = json.loads(cuerpo.decode("utf-8") or "{}")
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
        error(f"[webhook] Error leyendo el mensaje: {exc}")
    return {"ok": True}


def _clave_dueno(request: Request, datos: dict | None = None) -> bool:
    """¿Trae la clave de dueño (ADMIN_TOKEN)? Header, ?token= o body.

    Sin ADMIN_TOKEN configurado, siempre NO: los endpoints están
    cerrados hasta que el dueño ponga la clave en Render.
    """
    token = (
        request.headers.get("X-Admin-Token")
        or request.query_params.get("token")
        or (datos or {}).get("token")
    )
    return seguridad.token_admin_ok(token, settings.admin_token)


_PAGINA_PAUSA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pausa del robot</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;max-width:420px;margin:40px auto;padding:0 20px;color:#1d1d1f}}
h1{{font-size:22px}}p{{color:#6e6e73;line-height:1.5}}
input,button{{font-size:17px;padding:12px;width:100%;box-sizing:border-box;border-radius:10px}}
input{{border:1px solid #d2d2d7;margin:8px 0}}button{{background:#0071e3;color:#fff;border:0;margin-top:8px}}
.ok{{color:#1d7a1d}}</style></head><body>
<h1>Ya contesté yo</h1>
<p>Escribe el teléfono del cliente al que le contestaste. El robot se
callará en ese chat 2 horas y después vuelve solo, con todo el contexto.</p>
<form method="post"><input name="telefono" inputmode="tel" placeholder="Ej. 5216694608263" required>
<input type="hidden" name="token" value="{token}">
<button type="submit">Poner en pausa 2 horas</button></form>
{mensaje}</body></html>"""


@app.get("/pausa")
def pagina_pausa(request: Request):
    """La página del dueño: "ya contesté yo".

    Meta no avisa cuando el dueño contesta por WhatsApp, así que la
    pausa de 2 horas no puede ser automática: se activa aquí. El dueño
    guarda esta dirección en su teléfono (con ?token=SU_CLAVE) y cada
    vez que contesta a un cliente, pone el número y listo.
    """
    if not _clave_dueno(request):
        return HTMLResponse("<h1>Sin acceso</h1><p>Falta la clave de dueño (?token=...).</p>", status_code=403)
    token = request.query_params.get("token", "")
    return HTMLResponse(_PAGINA_PAUSA.format(token=token, mensaje=""))


@app.post("/pausa")
async def marcar_pausa(request: Request):
    """Marca que una persona atendió un chat: arranca la pausa de 2 horas.

    Acepta JSON ({"telefono": "...", "token": "..."}) o el formulario
    de la página GET /pausa. También puedes escribir la fecha directo
    en Control!B2 de la hoja.
    """
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        # El formulario del dueño se manda así por defecto. Se parsea a
        # mano para no depender de python-multipart en este camino.
        from urllib.parse import parse_qs

        cuerpo = await request.body()
        datos = {k: v[0] for k, v in parse_qs(cuerpo.decode("utf-8", "replace")).items()}
    elif "multipart/form-data" in content_type:
        form = await request.form()
        datos = dict(form)
    else:
        try:
            datos = await request.json()
        except Exception:
            datos = {}
    if not _clave_dueno(request, datos):
        return PlainTextResponse("Sin acceso: falta la clave de dueño.", status_code=403)
    telefono = str(datos.get("telefono", "")).strip()
    ahora = datetime.now(timezone.utc).isoformat()
    es_formulario = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
    # Si la hoja falla (sin credenciales, sin red), el dueño tiene que
    # saberlo: una pausa que no se guardó es peor que un error visible.
    try:
        sheets.actualizar_ultima_respuesta_humana(ahora)
        # También queda registrado que un humano habló en ese chat.
        sheets.registrar_conversacion(ahora, telefono, "humano", "(la persona atendió el chat)", "no", "humano activo hace menos de 2 horas")
    except Exception as exc:  # noqa: BLE001 - la pausa no se guardó
        error(f"[pausa] No pude guardar la pausa para {telefono}: {exc}")
        if es_formulario:
            token = str(datos.get("token", ""))
            mensaje = ('<p style="color:#b3261e">No se pudo guardar la pausa. '
                       'Revisa que el robot esté conectado a la hoja de Google.</p>')
            return HTMLResponse(_PAGINA_PAUSA.format(token=token, mensaje=mensaje))
        return {"ok": False, "error": str(exc)}
    if es_formulario:
        token = str(datos.get("token", ""))
        mensaje = f'<p class="ok">Listo. El robot está en pausa para {telefono} hasta dentro de 2 horas.</p>'
        return HTMLResponse(_PAGINA_PAUSA.format(token=token, mensaje=mensaje))
    return {"ok": True, "pausa_hasta": ahora, "telefono": telefono}


@app.post("/reporte-semanal")
async def reporte_ahora(request: Request):
    """Manda el reporte semanal ahora, sin esperar al lunes. Para probarlo.

    (v3.0) Protegido con la clave de dueño: sin ella, 403.
    """
    if not _clave_dueno(request):
        return PlainTextResponse("Sin acceso: falta la clave de dueño.", status_code=403)
    resultado = generar_reporte_semanal()
    return {"ok": True, "semana": resultado["semana"]}


@app.post("/resumen-manana")
async def resumen_ahora(request: Request):
    """Manda el resumen de la mañana ahora, sin esperar a las 08:00. Para probarlo.

    (v3.3) Protegido con la clave de dueño: sin ella, 403.
    """
    if not _clave_dueno(request):
        return PlainTextResponse("Sin acceso: falta la clave de dueño.", status_code=403)
    resultado = generar_resumen_manana()
    return {"ok": True, "fecha": resultado["fecha"]}


# --- Trabajos programados: reporte semanal (lunes 08:00) y resumen
# de la mañana (todos los días 08:00). Manden correo, nunca WhatsApp.

scheduler = BackgroundScheduler(timezone=settings.timezone)
scheduler.add_job(
    generar_reporte_semanal,
    CronTrigger(day_of_week=settings.reporte_dia_semana, hour=settings.reporte_hora, minute=settings.reporte_minuto),
    id="reporte-semanal",
    replace_existing=True,
)
scheduler.add_job(
    generar_resumen_manana,
    CronTrigger(hour=settings.reporte_hora, minute=settings.reporte_minuto),
    id="resumen-manana",
    replace_existing=True,
)


@app.on_event("startup")
def arrancar():
    """Al arrancar: avisa si faltan claves, recupera lo pendiente y
    revisa la salud de cada pieza (ver robot/salud.py). Nada de esto
    bloquea el arranque: el robot prende aunque algo falle, y el fallo
    queda en Diagnóstico para que se vea en la hoja.
    """
    from robot.config import faltan_claves
    from robot.logic import cargar_propuestas

    faltantes = faltan_claves()
    if faltantes:
        aviso(f"AVISO: faltan en el .env: {', '.join(faltantes)}. Ver README.")
    else:
        info("Claves listas. Robot arrancado.")
    # (v2.5) Recuperar las propuestas guardadas en la hoja: si Render se
    # reinició, los clientes pueden confirmar igual sus citas pendientes.
    try:
        n = cargar_propuestas(_DEPS)
        if n:
            info(f"Recuperé {n} propuesta(s) de cita de la hoja.")
    except Exception as exc:  # noqa: BLE001 - sin propuestas, el robot sigue igual
        aviso(f"No pude recuperar propuestas de la hoja: {exc}")
    # (v3.0) Recuperar los lotes del buzón en disco: mensajes que
    # llegaron y no se alcanzaron a procesar antes del reinicio.
    try:
        n = _AGRUPADOR.cargar()
        if n:
            info(f"Recuperé {n} lote(s) pendiente(s) del buzón.")
    except Exception as exc:  # noqa: BLE001 - sin buzón, el robot sigue igual
        aviso(f"No pude recuperar el buzón: {exc}")
    # (v3.0) Revisión de salud en segundo plano: Gemini, hoja,
    # calendario, token de WhatsApp, Gmail y claves de seguridad.
    # Antes solo se probaba Gemini; lo demás se descubría de noche.
    threading.Thread(target=salud.revisar_salud, args=(_DEPS,), daemon=True).start()
    scheduler.start()
    info(f"Reporte semanal programado: lunes {settings.reporte_hora:02d}:{settings.reporte_minuto:02d} ({settings.timezone}).")
    info(f"Resumen de la mañana programado: todos los días {settings.reporte_hora:02d}:{settings.reporte_minuto:02d} ({settings.timezone}).")


@app.on_event("shutdown")
def apagar():
    scheduler.shutdown()
