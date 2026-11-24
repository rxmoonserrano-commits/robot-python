"""Pruebas de la v3.5 (multi-negocio y canales): Configuración desde la hoja.

(a) leer_configuracion: filas clave|valor -> dict; sin pestaña -> {}.
(b) Defaults: sin Configuración, todo igual que siempre (Ana, amigable,
    interruptores en SI, sin extras en el guion).
(c) Overrides: la hoja manda — nombre, tono, saludo, interruptores
    aparecen en el guion y en el perfil.
(d) Interruptores en vivo: agendar=NO no propone citas ni con la red
    de seguridad; enviar_fotos=NO no manda fotos (el texto sale igual).
(e) Canales: WhatsApp siempre activo; Messenger/Instagram diseñados
    pero apagados (los adaptadores se niegan con CanalNoActivo).
(f) app.py trae las rutas /webhook/messenger y /webhook/instagram.

Sin internet: todo con fakes y parches, como las demás pruebas.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import robot.agent as agent_mod
import robot.canales as canales_mod
import robot.negocio as negocio_mod
import robot.sheets as sheets_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_mensaje

TEL = "6671234567"
AHORA = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)  # mié 09:00 Mazatlán
CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]
FECHA_OK = "2026-11-20T10:00:00"  # viernes 10:00, dentro de horario

TOTAL = [0]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    TOTAL[0] += 1
    if condicion:
        print(f"  ok  {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"FALLA {nombre} :: {detalle}")


class Deps35:
    """Servicios de mentira mínimos para probar los interruptores."""

    def __init__(self, agente=None, huecos=None):
        self.agente = agente or RespuestaAgente(respuesta_texto="Claro, te ayudo.")
        self.huecos = huecos or []
        self.textos = []
        self.fotos_env = []
        self.botones = []
        self.conversaciones = []
        self.clientes = []
        self.diagnosticos = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return None

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return FOTOS

    def leer_historial(self, telefono):
        return []

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"telefono": telefono, "quien_hablo": quien})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"telefono": telefono})

    def cancelar_cita_cliente(self, telefono):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append((componente, estado, detalle))

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        return self.agente

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        self.fotos_env.append((telefono, url))

    def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, texto, botones))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        inicio = datetime.fromisoformat(fecha_cita)
        return {"inicio": inicio.isoformat(), "fin": (inicio + timedelta(minutes=60)).isoformat()}

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def proximos_huecos_libres(self, conocimiento, ahora):
        return self.huecos

    def hora_libre(self, fecha_iso):
        return True

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen="", hilo=""):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


def _con_config(cfg):
    """Parchea la Configuración que lee negocio; devuelve el original."""
    orig = negocio_mod.configuracion
    negocio_mod.configuracion = lambda: dict(cfg)
    return orig


def _sin_config(orig):
    negocio_mod.configuracion = orig


# ---------- (a) leer_configuracion ----------

orig_leer = sheets_mod.leer_pestana
try:
    sheets_mod.leer_pestana = lambda pestana: [
        {"clave": "tono", "valor": "breve"},
        {"clave": "agendar", "valor": "NO"},
        {"clave": "", "valor": "ignorado"},
    ]
    cfg = sheets_mod.leer_configuracion()
    caso("(a) Filas clave|valor se vuelven dict (y se ignora la clave vacía)",
         cfg == {"tono": "breve", "agendar": "NO"}, repr(cfg))

    sheets_mod.leer_pestana = lambda pestana: []
    caso("(a) Pestaña vacía -> {} (defaults)", sheets_mod.leer_configuracion() == {})

    def _explota(pestana):
        raise RuntimeError("no hay pestaña")
    sheets_mod.leer_pestana = _explota
    caso("(a) Sin pestaña (error) -> {} sin romper",
         sheets_mod.leer_configuracion() == {})
finally:
    sheets_mod.leer_pestana = orig_leer

# ---------- (b) Defaults sin Configuración ----------

orig_cfg = _con_config({})
try:
    caso("(b) Sin config: tono amigable, interruptores SI, sin saludo",
         negocio_mod.tono() == "amigable"
         and negocio_mod.interruptor("agendar") is True
         and negocio_mod.interruptor("enviar_fotos") is True
         and negocio_mod.saludo_config() == ""
         and negocio_mod.mensaje_fuera_horario() == "")
    prompt = agent_mod.guion()
    caso("(b) Sin config: el guion no trae extras (comportamiento actual)",
         "Tono breve" not in prompt and "Saludo obligatorio" not in prompt
         and "la agenda está apagada" not in prompt
         and "la función de fotos está apagada" not in prompt,
         prompt[:300])
finally:
    _sin_config(orig_cfg)

# ---------- (c) Overrides desde la hoja ----------

orig_cfg = _con_config({
    "nombre_asistente": "Lupita",
    "nombre_negocio": "Taquería El Faro",
    "tipo_negocio": "una taquería",
    "tono": "breve",
    "saludo": "¡Qué tal! Soy Lupita, ¿en qué te ayudo?",
    "mensaje_fuera_horario": "Ya cerramos, pero te aparto tu lugar para mañana.",
    "agendar": "NO",
    "enviar_fotos": "NO",
})
try:
    caso("(c) La hoja manda: nombre, negocio, tono, interruptores",
         negocio_mod.nombre_recepcionista() == "Lupita"
         and negocio_mod.nombre_negocio() == "Taquería El Faro"
         and negocio_mod.tono() == "breve"
         and negocio_mod.interruptor("agendar") is False
         and negocio_mod.interruptor("enviar_fotos") is False)
    prompt = agent_mod.guion()
    caso("(c) El guion usa el perfil de la hoja y los extras",
         "Te llamas Lupita" in prompt
         and "de Taquería El Faro" in prompt
         and "Tono breve" in prompt
         and "¡Qué tal! Soy Lupita, ¿en qué te ayudo?" in prompt
         and "Ya cerramos, pero te aparto tu lugar para mañana." in prompt
         and "la agenda está apagada" in prompt
         and "la función de fotos está apagada" in prompt,
         prompt[:400])
finally:
    _sin_config(orig_cfg)

# ---------- (d) Interruptores en vivo ----------

# agendar=NO: el agente pide agendar, pero no se propone nada.
orig_cfg = _con_config({"agendar": "NO"})
try:
    d = Deps35(agente=RespuestaAgente(
        respuesta_texto="Perfecto, te agendo.", quiere_agendar="si",
        fecha_cita=FECHA_OK, motivo="Limpieza"))
    r = atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("(d) agendar=NO: no hay propuesta con botones ni cita_propuesta",
         not d.botones and not r.get("cita_propuesta") and bool(d.textos),
         f"botones={d.botones} r={r}")
finally:
    _sin_config(orig_cfg)

# agendar por defecto (SI): la propuesta sí sale (sanidad).
orig_cfg = _con_config({})
try:
    d = Deps35(agente=RespuestaAgente(
        respuesta_texto="Perfecto, te agendo.", quiere_agendar="si",
        fecha_cita=FECHA_OK, motivo="Limpieza"))
    r = atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("(d) agendar=SI (default): la propuesta con botones sí sale",
         bool(d.botones) and bool(r.get("cita_propuesta")),
         f"botones={d.botones} r={r}")
finally:
    _sin_config(orig_cfg)

# enviar_fotos=NO: la foto oficial no se manda; el texto sí.
orig_cfg = _con_config({"enviar_fotos": "NO"})
try:
    d = Deps35(agente=RespuestaAgente(
        respuesta_texto="Aquí está el local.",
        foto_oficial_url_or_null="https://ejemplo.com/foto-local.jpg"))
    atender_mensaje(d, TEL, "Ana", "¿cómo es el local?", con_ritmo=False, ahora=AHORA)
    caso("(d) enviar_fotos=NO: no se manda foto, pero sí el texto",
         not d.fotos_env and bool(d.textos), f"fotos={d.fotos_env}")
finally:
    _sin_config(orig_cfg)

# enviar_fotos por defecto: la foto oficial sí sale (sanidad).
orig_cfg = _con_config({})
try:
    d = Deps35(agente=RespuestaAgente(
        respuesta_texto="Aquí está el local.",
        foto_oficial_url_or_null="https://ejemplo.com/foto-local.jpg"))
    atender_mensaje(d, TEL, "Ana", "¿cómo es el local?", con_ritmo=False, ahora=AHORA)
    caso("(d) enviar_fotos=SI (default): la foto oficial sí se manda",
         len(d.fotos_env) == 1, f"fotos={d.fotos_env}")
finally:
    _sin_config(orig_cfg)

# ---------- (e) Canales ----------

os.environ.pop("CANAL_MESSENGER_ACTIVO", None)
os.environ.pop("CANAL_INSTAGRAM_ACTIVO", None)
caso("(e) WhatsApp siempre activo; Messenger/Instagram apagados por defecto",
     canales_mod.canal_activo("whatsapp") is True
     and canales_mod.canal_activo("messenger") is False
     and canales_mod.canal_activo("instagram") is False
     and canales_mod.canal_activo("otro") is False)

try:
    canales_mod.adaptador_messenger({"entry": []})
    caso("(e) Adaptador Messenger apagado se niega", False, "no lanzó")
except canales_mod.CanalNoActivo:
    caso("(e) Adaptador Messenger apagado se niega con CanalNoActivo", True)

try:
    canales_mod.enviar_instagram("123", "hola")
    caso("(e) Enviar por Instagram apagado se niega", False, "no lanzó")
except canales_mod.CanalNoActivo:
    caso("(e) Enviar por Instagram apagado se niega con CanalNoActivo", True)

msg = canales_mod.normalizar_mensaje("messenger", " 123 ", " hola ")
caso("(e) Mensaje normalizado con el formato único",
     msg["canal"] == "messenger" and msg["remitente"] == "123"
     and msg["texto"] == "hola" and msg["adjuntos"] == []
     and "recibido_en" in msg, repr(msg))

payload = {"entry": [{"messaging": [
    {"sender": {"id": "999"}, "message": {"text": "¿cuánto cuesta?"}},
    {"sender": {"id": "999"}, "delivery": {}},
]}]}
ev = canales_mod._extraer_messaging(payload)
caso("(e) El extractor saca solo mensajes reales (ignora entregas)",
     len(ev) == 1 and ev[0]["remitente"] == "999" and ev[0]["texto"] == "¿cuánto cuesta?",
     repr(ev))

# ---------- (f) Rutas en app.py ----------

app_txt = open("app.py", encoding="utf-8").read()
caso("(f) app.py trae las rutas de Messenger e Instagram (apagadas)",
     '"/webhook/messenger"' in app_txt and '"/webhook/instagram"' in app_txt
     and "canal_activo" in app_txt)

print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} pasaron")
if FALLOS:
    print("Fallaron:", ", ".join(FALLOS))
    sys.exit(1)
print("TODO VERDE en test_v3_5.py")
