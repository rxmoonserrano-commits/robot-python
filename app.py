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
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool

from robot import booking, estado_servidor, gemini, mail, salud, seguridad, sheets, whatsapp
from robot.abuso import Limitador
from robot.agent import preguntar_agente
from robot.agrupar import Agrupador
from robot.config import settings
from robot.cola_durable import ColaDurable
from robot.trabajador_cola import TrabajadorCola
from robot.logic import Dependencias, atender_boton, atender_mensaje
from robot.registro import aviso, configurar as configurar_registro, error, info
from robot.vigilancia import LOTE_LENTO_SEGUNDOS, con_vigilancia
from robot.report import generar_reporte_semanal, generar_reporte_mensual, generar_resumen_manana

configurar_registro()

VERSION = "3.22.1"


# El ciclo de vida del servidor. FastAPI ya no recomienda @app.on_event
# (deprecated); se usa el contexto `lifespan`: arrancar() antes de
# recibir tráfico y apagar() al cerrar (lo definen más abajo, se
# resuelven al ejecutar el ciclo de vida, cuando el módulo ya está
# completo).
@asynccontextmanager
async def _ciclo_vida(app):
    arrancar()
    yield
    apagar()


app = FastAPI(title="Robot WhatsApp — IA gratis", version=VERSION,
              lifespan=_ciclo_vida)


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

    def leer_pausa_hasta(self, telefono):
        return sheets.leer_pausa_hasta(telefono)

    def pausar_conversacion(self, telefono, hasta):
        sheets.pausar_conversacion(telefono, hasta)

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        sheets.registrar_conversacion(fecha, telefono, quien, mensaje, respondio, motivo)

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp", estatus="en conversacion", handoff="no"):
        sheets.registrar_cliente(fecha, nombre, telefono, motivo, fecha_cita, origen, estatus, handoff)

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        return preguntar_agente(mensaje, conocimiento, fotos, historial)

    def enviar_texto(self, telefono, texto):
        whatsapp.enviar_texto(telefono, texto)

    def enviar_plantilla(self, telefono, plantilla, idioma, parametros):
        whatsapp.enviar_plantilla(telefono, plantilla, idioma, parametros)

    def enviar_foto(self, telefono, url):
        whatsapp.enviar_foto(telefono, url)

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        # (v3.9) La cita dura lo que diga la hoja para ese servicio
        # (columna Duración_min); sin dato, el default de 60.
        dur = None
        try:
            dur = sheets.duracion_servicio(motivo)
        except Exception:
            dur = None
        return booking.crear_cita(nombre, telefono, motivo, fecha_cita,
                                  duracion_min=dur, nota=nota)

    def duracion_servicio(self, motivo):
        try:
            return sheets.duracion_servicio(motivo)
        except Exception:
            return None

    def registrar_cita_espejo(self, fila):
        try:
            sheets.registrar_cita_espejo(fila)
        except Exception as exc:  # noqa: BLE001 - el espejo nunca rompe WhatsApp
            aviso(f"[citas-espejo] {exc}")

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None,
                               recordatorio_enviado=None, urgencia=None,
                               nueva_fecha=None, nueva_hora_inicio=None,
                               nueva_hora_fin=None):
        try:
            sheets.actualizar_cita_espejo(telefono, fecha_cita, estado, notas,
                                          recordatorio_enviado, urgencia,
                                          nueva_fecha, nueva_hora_inicio,
                                          nueva_hora_fin)
        except Exception as exc:  # noqa: BLE001 - el espejo nunca rompe WhatsApp
            aviso(f"[citas-espejo] {exc}")

    def leer_citas_espejo(self):
        try:
            return sheets.leer_citas_espejo()
        except Exception as exc:  # noqa: BLE001 - sin espejo, el tope usa Clientes
            aviso(f"[citas-espejo] {exc}")
            return []

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        try:
            sheets.actualizar_cita_espejo(telefono, fecha_cita, None, notas)
        except Exception as exc:  # noqa: BLE001 - el espejo nunca rompe WhatsApp
            aviso(f"[citas-espejo] {exc}")

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        try:
            mail.alerta_cita_pendiente(nombre, telefono, motivo, fecha_bonita, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    def hora_libre(self, fecha_iso):
        # Propagar los fallos: el llamador no debe afirmar disponibilidad
        # si Calendar no pudo verificarla.
        return booking.hora_libre(fecha_iso)

    def existe_cita_en_calendario(self, telefono, fecha_iso):
        # (v3.20.4) Reconciliación al arrancar: ¿la cita de esta
        # propuesta ya existe en el calendario? Si el calendario
        # falla, False (sin evidencia: la propuesta se conserva).
        try:
            return booking.existe_cita(telefono, fecha_iso)
        except Exception:
            return False

    def cancelar_cita(self, telefono, fecha_cita):
        return booking.cancelar_cita(telefono, fecha_cita)

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias="", miedos="",
                                acompanante="", correo=""):
        sheets.guardar_memoria_cliente(telefono, resumen, interes,
                                       proxima_accion, preferencias, miedos,
                                       acompanante, correo)

    def actualizar_nombre_cliente(self, telefono, nombre):
        # (v3.20.9) El nombre confirmado por el cliente manda sobre
        # el de perfil de WhatsApp (se escribe directo en Clientes B).
        sheets.actualizar_nombre_cliente(telefono, nombre)

    def leer_clientes(self):
        # (v3.20.7) Para el seguimiento proactivo. Sin Clientes, el
        # seguimiento no encuentra a nadie y no manda nada.
        try:
            return sheets.leer_pestana("Clientes")
        except Exception as exc:  # noqa: BLE001 - sin clientes, no hay seguimiento
            aviso(f"[clientes] {exc}")
            return []

    def guardar_propuesta(self, telefono, propuesta):
        sheets.guardar_propuesta(telefono, propuesta)

    def borrar_propuesta(self, telefono):
        sheets.borrar_propuesta(telefono)

    def leer_propuestas(self):
        return sheets.leer_propuestas()

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen="", hilo=""):
        # Best-effort también aquí (doble protección, ver logic.py):
        # si Gmail no está configurado, el correo no debe romper nada.
        # (v3.20.3) Faltaba el parámetro hilo: logic.py lo pasa desde
        # v3.20 y el TypeError se tragaba en silencio, así que los
        # correos de handoff NUNCA salían en producción.
        try:
            mail.alerta_handoff(nombre, telefono, motivo, ultimo_mensaje, fecha, resumen, hilo)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    # --- Nuevos en la v3.3 ---
    def proximos_huecos_libres(self, conocimiento, ahora, cantidad=2, dias=3):
        from robot.logic import horarios_por_dia

        return booking.proximos_huecos_libres(
            horarios_por_dia(conocimiento), ahora,
            cantidad=cantidad, dias=dias,
        )

    def proximos_huecos_profesionales(self, conocimiento, ahora, cantidad=2, dias=3):
        # (v3.12) Agenda por profesional: sin profesionales activos con
        # horario, devuelve [] y el robot usa la agenda por clínica.
        try:
            profesionales = sheets.leer_profesionales()
            if not profesionales:
                return []
            return booking.proximos_huecos_por_profesional(
                profesionales, ahora, cantidad=cantidad, dias=dias,
            )
        except Exception:
            return []

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        try:
            mail.alerta_cita_confirmada(nombre, telefono, motivo, fecha_bonita, fecha)
        except Exception as exc:  # noqa: BLE001 - el correo nunca rompe WhatsApp
            aviso(f"[correo] No se pudo avisar por correo (el robot sigue): {exc}")

    def alerta_cita_urgente(self, nombre, telefono, motivo, fecha_bonita, fecha, razon=""):
        try:
            mail.alerta_cita_urgente(nombre, telefono, motivo, fecha_bonita, fecha, razon)
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
    # (v3.9.1) Bandera compartida con el vigilante: si el lote tarda
    # más de 90 s, el vigilante manda el "dame un momento" y pone la
    # bandera; si después la respuesta es una falla técnica, logic.py
    # no manda el mismo texto otra vez (el cliente recibía dos
    # burbujas idénticas).
    aviso_lote = {"si": False}

    def _avisar_lote_lento():
        """El lote lleva más de 90 s: que se vea y que el cliente sepa.

        (v3.1) El 12 de noviembre un lote se quedó más de 45 minutos
        sin responder ni fallar, sin dejar rastro en ningún lado. Con
        vigilancia, a los 90 s queda en Diagnóstico y el cliente
        recibe un "dame un momento"; la respuesta real llega igual
        cuando el trabajo termine.
        """
        aviso_lote["si"] = True
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
        estado_servidor.contar_lote_inicio()
        con_vigilancia(
            lambda: atender_mensaje(_DEPS, telefono, nombre, texto_unido, message_id=primer_wamid, aviso_lote_enviado=aviso_lote),
            _avisar_lote_lento,
            segundos=LOTE_LENTO_SEGUNDOS,
        )
        estado_servidor.contar_lote_fin(True)
    except Exception as exc:  # noqa: BLE001 - nunca dejar al cliente sin respuesta
        estado_servidor.contar_lote_fin(False, str(exc))
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

# (v3.20.4) Los botones también tienen su límite, en un contador
# aparte (para no contaminar el de textos): 30 toques en 60 s está
# muy por encima de cualquier flujo legítimo (una propuesta se toca
# 1-3 veces), y frena a quien toque sin parar para inundar
# WhatsApp y correos.
_LIMITADOR_BOTONES = Limitador(max_mensajes=30, ventana_segundos=60.0)


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
    # (v3.4.8) Visto instantáneo: en cuanto llega el mensaje, se marca
    # como leído (palomitas azules), antes de esperar los 15 segundos
    # del buffer. Es lo que Jose pidió: que se sienta atendido desde el
    # primer segundo. Best-effort: si falla, el mensaje sigue su curso.
    if wamid:
        try:
            whatsapp.marcar_leido(wamid)
        except Exception as exc:  # noqa: BLE001 - el visto nunca rompe el webhook
            aviso(f"[visto] No pude marcar leído {wamid} de {telefono}: {exc}")
        # (v3.9.2) La burbuja también sale desde el primer segundo:
        # el cliente ve "escribiendo..." en cuanto manda el mensaje,
        # no después de la espera del buffer. La burbuja dura ~25 s y
        # se apaga sola; cuando el lote arranca, atender_mensaje la
        # vuelve a prender (paso 3) y ya no se refresca: si la
        # respuesta tarda más, la burbuja se apaga como la de una
        # persona que dejó de escribir, y la respuesta llega cuando
        # está lista. Best-effort: si el robot va a quedarse callado
        # (pausa, apagado), la burbuja solo se apaga a los 25 s.
        try:
            whatsapp.marcar_leido_y_escribiendo(wamid)
        except Exception as exc:  # noqa: BLE001 - la burbuja nunca rompe el webhook
            aviso(f"[escribiendo] No pude prender la burbuja {wamid} de {telefono}: {exc}")
    if tipo == "interactive":
        boton = mensaje.get("interactive", {}).get("button_reply", {})
        boton_id = boton.get("id", "")
        if not boton_id:
            return
        # (v3.20.4) Dedup: si Meta reenvía el mismo tap (mismo
        # wamid), no se atiende dos veces. Antes el botón no pasaba
        # por ningún dedup: un reenvío podía mandar el correo de
        # handoff dos veces.
        if wamid and not _AGRUPADOR.marcar_visto(wamid):
            return
        # (v3.20.4) Anti-abuso también para botones: si el teléfono
        # está en ráfaga de toques, el tap se ignora en silencio.
        # La propuesta queda pendiente; un toque después de la
        # ventana funciona normal.
        if _LIMITADOR_BOTONES.registrar(telefono) != "ok":
            return
        try:
            # (v3.20.3) Si el cliente mandó textos que aún están en
            # el buzón de agrupamiento, se atienden primero: el
            # botón no se salta la fila y el lote no se procesa
            # después sobre una propuesta ya consumida.
            try:
                _AGRUPADOR.procesar_ahora(telefono)
            except Exception:
                pass
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
            # (v3.20.4) Se marca el wamid como visto: si Meta reenvía
            # este mismo audio, no se le manda el aviso dos veces.
            if wamid:
                _AGRUPADOR.marcar_visto(wamid)
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
        # (v3.4.6) El registro dice en palabras claras qué mandó el
        # cliente: si luego pregunta "¿qué recibiste?", el robot lo sabe
        # por el historial y no inventa (en vivo inventó "un sticker
        # del sistema" porque el registro decía solo "(image recibido)").
        # (v3.20.4) Mismo dedup que el audio: un reenvío de Meta no
        # repite la respuesta.
        if wamid:
            _AGRUPADOR.marcar_visto(wamid)
        _responder_directo(
            telefono,
            "Gracias, lo recibí. ¿Me cuentas con tus palabras qué necesitas? Así te ayudo mejor.",
            f"(el cliente mandó un mensaje que no es texto ({tipo}); "
            "el robot no lo puede ver, solo texto)",
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
    _AGRUPADOR.agregar(telefono, texto, wamid=wamid, nombre=nombre,
                       timestamp=mensaje.get("timestamp"))


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


def _procesar_lote_durable(filas: list[tuple[int, str, dict]]) -> None:
    """Procesa un lote de un teléfono sin usar el buzón local efímero."""
    mensaje_primero = filas[0][2]["mensaje"]
    telefono = str(mensaje_primero.get("from") or "")
    nombre = ""
    for _, _, contenido in filas:
        for contacto in contenido.get("contacts", []):
            if contacto.get("wa_id") == telefono:
                nombre = contacto.get("profile", {}).get("name", "") or nombre
    tipo = mensaje_primero.get("type", "")
    if tipo == "interactive":
        interactivo = mensaje_primero.get("interactive")
        interactivo = interactivo if isinstance(interactivo, dict) else {}
        seleccion = interactivo.get("button_reply") or interactivo.get("list_reply") or {}
        seleccion = seleccion if isinstance(seleccion, dict) else {}
        boton_id = str(seleccion.get("id") or "").strip()
        if boton_id:
            atender_boton(_DEPS, telefono, nombre, boton_id)
            return
        # Un tipo interactivo desconocido no debe bloquear el chat para
        # siempre. Se procesa abajo como contenido no legible; si una
        # excepción llega al trabajador, se conserva para reintento.
    textos = []
    for _, _, contenido in filas:
        mensaje = contenido["mensaje"]
        tipo = mensaje.get("type", "")
        if tipo == "text":
            texto = str(mensaje.get("text", {}).get("body") or "")
        elif tipo == "audio":
            try:
                audio, mime = whatsapp.descargar_audio(mensaje.get("audio", {}).get("id", ""))
                texto = gemini.transcribir_audio(audio, mime)
            except Exception as exc:
                aviso(f"[audio] No se pudo transcribir: {type(exc).__name__}")
                texto = ""
            if not texto:
                texto = "(El cliente envió un audio que no se pudo transcribir; pídele que lo escriba.)"
        else:
            texto = "(El cliente envió un contenido que no se puede leer; pídele que lo explique por escrito.)"
        if texto:
            textos.append(texto)
    if textos:
        estado_servidor.contar_lote_inicio()
        try:
            atender_mensaje(_DEPS, telefono, nombre, "\n".join(textos), message_id=filas[0][1])
        except Exception as exc:
            estado_servidor.contar_lote_fin(False, type(exc).__name__)
            raise
        estado_servidor.contar_lote_fin(True)


_COLA = ColaDurable()
_TRABAJADOR = TrabajadorCola(_COLA, _procesar_lote_durable,
                             espera_segundos=settings.espera_agrupar_segundos)


# --- Endpoints ---


@app.get("/health")
def health():
    """¿Está vivo? Devuelve ok, la versión y la hora. Úsalo para probar que arrancó."""
    return {"ok": True, "version": VERSION, "hora": datetime.now(timezone.utc).isoformat()}


@app.get("/estado")
def estado():
    """¿Está vivo POR DENTRO? Lo que /health no dice: si el chequeo de
    salud terminó, cuántos mensajes llegaron al webhook, cuántos lotes
    se procesaron y cuántos fallaron, y cuál fue el último error.
    Solo números, sin teléfonos ni datos de clientes (v3.4)."""
    foto = estado_servidor.foto()
    foto["version"] = VERSION
    foto["lotes_pendientes"] = _AGRUPADOR.pendientes()
    foto["lotes_procesando"] = _AGRUPADOR.procesando()
    return foto


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


# --- Canales diseñados pero apagados (v3.5): Messenger e Instagram ---
# Las rutas existen para que la capacidad esté pensada y lista. Por
# ahora responden "activo: false" sin procesar nada: no se conecta
# ningún canal hasta que Jose lo decida (ver robot/canales.py).


@app.get("/webhook/messenger")
def verificar_messenger(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
):
    """Verificación de Meta para Messenger (misma lógica que WhatsApp)."""
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token incorrecto", status_code=403)


@app.post("/webhook/messenger")
async def recibir_messenger(request: Request):
    """Messenger: diseñado, apagado. No procesa nada por ahora."""
    from robot.canales import canal_activo

    if not canal_activo("messenger"):
        return {"ok": True, "canal": "messenger", "activo": False}
    return {"ok": True, "canal": "messenger", "activo": True,
            "pendiente": "procesamiento por conectar"}


@app.get("/webhook/instagram")
def verificar_instagram(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
):
    """Verificación de Meta para Instagram (misma lógica que WhatsApp)."""
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token incorrecto", status_code=403)


@app.post("/webhook/instagram")
async def recibir_instagram(request: Request):
    """Instagram: diseñado, apagado. No procesa nada por ahora."""
    from robot.canales import canal_activo

    if not canal_activo("instagram"):
        return {"ok": True, "canal": "instagram", "activo": False}
    return {"ok": True, "canal": "instagram", "activo": True,
            "pendiente": "procesamiento por conectar"}


@app.post("/webhook")
async def recibir_whatsapp(request: Request):
    """Valida la firma y persiste el lote antes de devolver 200.

    La conversación se procesa después, en un trabajador serial. Una
    falla de Sheets produce 503 para que Meta pueda reintentar.
    """
    cuerpo = await request.body()
    # Sin secreto no se puede autenticar a Meta: fallar cerrado también
    # evita aceptar tráfico malicioso durante una configuración incompleta.
    if not settings.meta_app_secret:
        error("[webhook] META_APP_SECRET no está configurado")
        return PlainTextResponse("Webhook no configurado", status_code=503)
    if not seguridad.verificar_firma_meta(
        cuerpo,
        request.headers.get("X-Hub-Signature-256"),
        settings.meta_app_secret,
    ):
        return PlainTextResponse("Firma inválida", status_code=403)
    try:
        datos = json.loads(cuerpo.decode("utf-8") or "{}")
        mensajes = []
        for entrada in datos.get("entry", []):
            for cambio in entrada.get("changes", []):
                valor = cambio.get("value", {})
                mensajes.extend((mensaje, valor) for mensaje in valor.get("messages", []))
    except (ValueError, UnicodeDecodeError, AttributeError, TypeError):
        return PlainTextResponse("Notificación inválida", status_code=400)
    if mensajes:
        try:
            # La llamada bloqueante va al pool, no al bucle asíncrono.
            nuevos = await run_in_threadpool(_COLA.guardar, mensajes)
        except Exception as exc:
            error(f"[webhook] No se pudo guardar en Sheets: {type(exc).__name__}")
            return PlainTextResponse("No se pudo guardar el mensaje", status_code=503)
        for _ in range(nuevos):
            estado_servidor.contar_webhook()
        _TRABAJADOR.avisar()
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

    La derivación del robot pausa automáticamente ese teléfono. Si el
    dueño inicia una atención por su cuenta, puede activar aquí la pausa
    manual sin detener las demás conversaciones.
    """
    if not _clave_dueno(request):
        return HTMLResponse("<h1>Sin acceso</h1><p>Falta la clave de dueño (?token=...).</p>", status_code=403)
    token = request.query_params.get("token", "")
    return HTMLResponse(_PAGINA_PAUSA.format(token=token, mensaje=""))


@app.post("/pausa")
async def marcar_pausa(request: Request):
    """Marca que una persona atendió un chat: arranca la pausa de 2 horas.

    Acepta JSON ({"telefono": "...", "token": "..."}) o el formulario
    de la página GET /pausa. Guarda la pausa para ese teléfono en
    Conversaciones; no modifica la pausa global heredada de Control.
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
    if not telefono.isdigit():
        return PlainTextResponse("Teléfono inválido", status_code=400)
    ahora = datetime.now(timezone.utc).isoformat()
    es_formulario = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
    # Si la hoja falla (sin credenciales, sin red), el dueño tiene que
    # saberlo: una pausa que no se guardó es peor que un error visible.
    try:
        hasta = (datetime.fromisoformat(ahora) + timedelta(hours=settings.pausa_humano_horas)).isoformat()
        sheets.pausar_conversacion(telefono, hasta)
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
    return {"ok": True, "pausa_hasta": hasta, "telefono": telefono}


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


# --- Trabajos programados: reporte semanal (lunes 08:00), resumen
# de la mañana (todos los días 08:00) y recordatorios (cada hora,
# v3.12). El reporte y el resumen mandan correo, nunca WhatsApp;
# los recordatorios sí son WhatsApp (plantilla aprobada, Sereno 03).


def enviar_recordatorios_programados():
    """Revisa las citas de las próximas ~24 h y manda recordatorios.

    Best-effort total: si algo falla, queda en Diagnóstico y el
    robot sigue. El interruptor `recordatorios` de Configuración
    decide (sin él, la matriz de paquetes).
    """
    try:
        from robot import recordatorios

        recordatorios.enviar_recordatorios_pendientes(_DEPS)
    except Exception as exc:  # noqa: BLE001 - el job nunca tumba el robot
        aviso(f"[recordatorios] {exc}")


def enviar_seguimientos_programados():
    """Seguimiento proactivo (v3.20.7): clientes que preguntaron y no
    agendaron. Apagado por defecto: el interruptor
    `seguimiento_proactivo` de Configuración decide, y sin plantilla
    aprobada en Meta no manda nada real.
    """
    try:
        from robot import seguimiento

        seguimiento.enviar_seguimientos_pendientes(_DEPS)
    except Exception as exc:  # noqa: BLE001 - el job nunca tumba el robot
        aviso(f"[seguimiento] {exc}")


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
scheduler.add_job(
    generar_reporte_mensual,
    CronTrigger(day=settings.reporte_mensual_dia, hour=settings.reporte_hora, minute=settings.reporte_minuto),
    id="reporte-mensual",
    replace_existing=True,
)
scheduler.add_job(
    enviar_recordatorios_programados,
    IntervalTrigger(hours=1),
    id="recordatorios",
    replace_existing=True,
)
scheduler.add_job(
    enviar_seguimientos_programados,
    IntervalTrigger(hours=1),
    id="seguimiento",
    replace_existing=True,
)


def _mensajes_sin_respuesta(filas, ahora=None, ventana_horas: float = 12.0) -> dict:
    """(v3.20.14) Mensajes de cliente sin respuesta, para recuperar.

    Función pura (sin Sheets ni red): recibe las filas de Conversaciones
    (dicts con fecha, telefono, quien_hablo, mensaje, robot_respondio,
    motivo) y devuelve {telefono: [textos sin respuesta, en orden]}.

    Reglas:
    - Solo filas dentro de la ventana (últimas `ventana_horas` horas):
      un reinicio mata mensajes de minutos, no de días; sin esto se
      resucitarían pruebas viejas.
    - Un mensaje de cliente cuenta como respondido si DESPUÉS hay una
      fila de robot o humano para ese teléfono.
    - Se saltan los silencios intencionales (robot_respondio == "no":
      pausa humana, robot apagado, canal apagado): reprocesarlos solo
      volvería a callar. Los botones ("(botón ...)" con "no") también
      quedan fuera por la misma regla.
    """
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora.timestamp() - ventana_horas * 3600
    por_telefono: dict[str, list[dict]] = {}
    for fila in filas or []:
        try:
            fecha = datetime.fromisoformat(str(fila.get("fecha") or ""))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            ts = fecha.timestamp()
        except (ValueError, TypeError):
            continue
        if ts < desde:
            continue
        telefono = str(fila.get("telefono") or "").strip()
        if not telefono:
            continue
        por_telefono.setdefault(telefono, []).append(fila)
    sin_respuesta: dict[str, list[str]] = {}
    for telefono, lista in por_telefono.items():
        ultimo_indice_respuesta = -1
        for i, fila in enumerate(lista):
            if str(fila.get("quien_hablo") or "").strip() in ("robot", "humano"):
                ultimo_indice_respuesta = i
        pendientes = []
        for fila in lista[ultimo_indice_respuesta + 1:]:
            if str(fila.get("quien_hablo") or "").strip() != "cliente":
                continue
            if str(fila.get("robot_respondio") or "").strip().lower() == "no":
                continue  # silencio intencional: no se recupera
            texto = str(fila.get("mensaje") or "").strip()
            if texto:
                pendientes.append(texto)
        # (v3.20.15) Sin duplicados: si un reinicio re-registró el
        # mismo mensaje (visto 2026-11-25: el bucle de reinicios
        # registró "Hola buenas tardes" varias veces), no se
        # recupera varias veces. Se conserva el orden.
        vistos_texto: set[str] = set()
        unicos: list[str] = []
        for texto in pendientes:
            if texto not in vistos_texto:
                vistos_texto.add(texto)
                unicos.append(texto)
        pendientes = unicos
        if pendientes:
            sin_respuesta[telefono] = pendientes
    return sin_respuesta


def _esperar_salud_para_recuperar(intentos: int = 60,
                                  espera_segundos: float = 5.0) -> None:
    """(v3.20.15) Espera a que el chequeo de salud termine, con tope.

    Al arrancar, el chequeo de salud ya hace llamadas a
    Gemini/Sheets/WhatsApp. Si la recuperación de mensajes mete
    lotes en el mismo momento, el pico de memoria supera el límite
    del plan gratuito de Render y el servicio se reinicia en bucle
    (visto en vivo 2026-11-25). Por eso la recuperación espera a
    que la salud esté lista. El tope (60 × 5 s = 5 min) evita que
    un chequeo colgado deje los mensajes sin recuperar para
    siempre: pasado el tope, se recupera igual.
    """
    for _ in range(intentos):
        if estado_servidor.foto().get("salud_lista"):
            return
        time.sleep(espera_segundos)


def _recuperar_sin_respuesta(ahora=None) -> None:
    """(v3.20.14) Recupera mensajes que un reinicio dejó sin respuesta.

    El buzón en disco (buzon.json) solo guarda lotes PENDIENTES (en la
    ventana de agrupamiento); si Render se reinicia a mitad de un lote
    en proceso, ese mensaje se perdía (visto en vivo 2026-11-25: dos
    mensajes quedaron registrados sin respuesta). La hoja
    Conversaciones sí sobrevive a cualquier reinicio: aquí se busca
    ahí lo que quedó sin respuesta y se vuelve a meter al Agrupador,
    como si acabara de llegar. Best-effort: nunca tumba el arranque.
    (v3.20.15) Se procesa de a un teléfono (procesar_ahora espera a
    que cada lote termine) y sin textos duplicados: la primera
    versión metía todos los lotes a la vez al arrancar y el pico de
    memoria reiniciaba el servicio en bucle.
    `ahora` es para pruebas (la ventana de 12 h se mide contra él);
    en producción va None y se usa la hora real.
    """
    try:
        filas = sheets.leer_pestana("Conversaciones")
        pendientes = _mensajes_sin_respuesta(filas, ahora=ahora)
        if not pendientes:
            return
        total = 0
        for telefono, textos in pendientes.items():
            for texto in textos:
                _AGRUPADOR.agregar(telefono, texto)
            # (v3.20.15) De a un teléfono, en este hilo: procesar_ahora
            # despacha el lote ya y espera a que termine, así los lotes
            # recuperados nunca corren en paralelo entre sí (el pico
            # de memoria tumbó el servicio el 2026-11-25).
            _AGRUPADOR.procesar_ahora(telefono)
            total += len(textos)
        info(f"Recuperé {total} mensaje(s) sin respuesta de "
             f"{len(pendientes)} teléfono(s) de la hoja.")
        try:
            sheets.registrar_diagnostico(
                datetime.now(timezone.utc), "recuperacion", "AVISO",
                f"Recuperé {total} mensaje(s) sin respuesta de {len(pendientes)} "
                "teléfono(s) (reinicio a mitad de lote).", "", "")
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - la recuperación nunca tumba el arranque
        aviso(f"No pude recuperar mensajes sin respuesta de la hoja: {exc}")


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
    # El buzón anterior no tiene IDs durables. Reprocesarlo junto con la
    # nueva cola podría duplicar efectos: la migración exige vaciarlo y
    # reconciliar Conversaciones antes de activar esta versión.
    def _trabajar_tras_salud():
        _esperar_salud_para_recuperar()
        _TRABAJADOR.ejecutar()

    threading.Thread(target=_trabajar_tras_salud, daemon=True).start()
    # (v3.0) Revisión de salud en segundo plano: Gemini, hoja,
    # calendario, token de WhatsApp, Gmail y claves de seguridad.
    # Antes solo se probaba Gemini; lo demás se descubría de noche.
    # (v3.4) Al terminar se marca en /estado: si el chequeo nunca
    # termina (p. ej. Gemini colgado), se ve en segundos.
    def _salud_y_marca():
        try:
            salud.revisar_salud(_DEPS)
        finally:
            estado_servidor.marcar_salud_lista()

    threading.Thread(target=_salud_y_marca, daemon=True).start()
    scheduler.start()
    info(f"Reporte semanal programado: lunes {settings.reporte_hora:02d}:{settings.reporte_minuto:02d} ({settings.timezone}).")
    info(f"Resumen de la mañana programado: todos los días {settings.reporte_hora:02d}:{settings.reporte_minuto:02d} ({settings.timezone}).")


def apagar():
    _TRABAJADOR.cerrar()
    scheduler.shutdown()
