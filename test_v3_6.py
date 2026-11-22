"""Pruebas de la v3.6 (paquetes y canales por negocio).

(a) Paquetes: básico bloquea agenda/fotos/reportes; pro permite todo;
    el interruptor explícito manda sobre el paquete; sin paquete ni
    interruptores, todo en SI (compatibilidad).
(b) Canales por negocio: WhatsApp en SI por defecto, los demás en NO;
    un NO explícito apaga WhatsApp.
(c) Documento maestro: la fila del Índice (por clave) manda paquete
    y canales; sin variables o sin fila, no cambia nada.
(d) Cortes en vivo: paquete básico no propone citas; canal WhatsApp
    apagado = el robot no contesta; reportes omitidos en básico.

Sin internet: todo con fakes y parches, como las demás pruebas.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import robot.negocio as negocio_mod
import robot.report as report_mod
import robot.sheets as sheets_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_mensaje

TEL = "6671234567"
AHORA = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)
CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]
FECHA_OK = "2026-11-20T10:00:00"

TOTAL = [0]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    TOTAL[0] += 1
    if condicion:
        print(f"  ok  {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"FALLA {nombre} :: {detalle}")


class Deps36:
    """Servicios de mentira mínimos para probar los cortes por paquete/canal."""

    def __init__(self, agente=None):
        self.agente = agente or RespuestaAgente(respuesta_texto="Claro, te ayudo.")
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
        return []

    def hora_libre(self, fecha_iso):
        return True

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


def _con_config(cfg):
    orig = negocio_mod.configuracion
    negocio_mod.configuracion = lambda: dict(cfg)
    return orig


def _sin_config(orig):
    negocio_mod.configuracion = orig


# ---------- (a) Paquetes ----------

orig = _con_config({"paquete": "basico"})
try:
    caso("(a) Básico: sin agenda, sin fotos, sin reportes; sí FAQs y handoff",
         negocio_mod.paquete() == "basico"
         and negocio_mod.funcion_activa("agendar") is False
         and negocio_mod.funcion_activa("enviar_fotos") is False
         and negocio_mod.funcion_activa("reportes") is False
         and negocio_mod.funcion_activa("responder_faqs") is True
         and negocio_mod.funcion_activa("derivar_humano") is True)
finally:
    _sin_config(orig)

orig = _con_config({"paquete": "pro"})
try:
    caso("(a) Pro: agenda, fotos y reportes en SI",
         negocio_mod.funcion_activa("agendar") is True
         and negocio_mod.funcion_activa("enviar_fotos") is True
         and negocio_mod.funcion_activa("reportes") is True)
finally:
    _sin_config(orig)

orig = _con_config({"paquete": "basico", "agendar": "SI"})
try:
    caso("(a) El interruptor explícito manda sobre el paquete",
         negocio_mod.funcion_activa("agendar") is True)
finally:
    _sin_config(orig)

orig = _con_config({})
try:
    caso("(a) Sin paquete ni interruptores: todo en SI (compatibilidad)",
         negocio_mod.paquete() == ""
         and negocio_mod.funcion_activa("agendar") is True
         and negocio_mod.funcion_activa("reportes") is True)
finally:
    _sin_config(orig)

# ---------- (b) Canales por negocio ----------

orig = _con_config({})
try:
    caso("(b) Por defecto: WhatsApp SI, Messenger/Instagram NO",
         negocio_mod.canal_negocio_activo("whatsapp") is True
         and negocio_mod.canal_negocio_activo("messenger") is False
         and negocio_mod.canal_negocio_activo("instagram") is False)
finally:
    _sin_config(orig)

orig = _con_config({"canal_whatsapp": "NO", "canal_messenger": "SI"})
try:
    caso("(b) Switches explícitos: WhatsApp apagado, Messenger prendido",
         negocio_mod.canal_negocio_activo("whatsapp") is False
         and negocio_mod.canal_negocio_activo("messenger") is True)
finally:
    _sin_config(orig)

# ---------- (c) Documento maestro ----------

os.environ.pop("NEGOCIOS_SHEET_ID", None)
os.environ.pop("NEGOCIO_CLAVE", None)
caso("(c) Sin variables de maestro: no cambia nada",
     negocio_mod._config_maestra() == {})

os.environ["NEGOCIOS_SHEET_ID"] = "MAESTRO-TEST"
os.environ["NEGOCIO_CLAVE"] = "clinica-test"
orig_leer = sheets_mod.leer_pestana
orig_cfg_op = sheets_mod.leer_configuracion
try:
    sheets_mod.leer_pestana = lambda pestana, spreadsheet_id=None: [
        {"Negocio": "Clínica Test", "Clave": "clinica-test", "Paquete": "basico",
         "WhatsApp": True, "Messenger": False, "Instagram": False},
        {"Negocio": "Otro", "Clave": "otro", "Paquete": "pro",
         "WhatsApp": True, "Messenger": True, "Instagram": True},
    ]
    sheets_mod.leer_configuracion = lambda: {"paquete": "pro", "tono": "breve"}
    cfg = negocio_mod.configuracion()
    caso("(c) El maestro manda paquete y canales; la hoja manda lo demás",
         cfg.get("paquete") == "basico"
         and cfg.get("canal_whatsapp") == "SI"
         and cfg.get("canal_messenger") == "NO"
         and cfg.get("tono") == "breve",
         repr(cfg))

    os.environ["NEGOCIO_CLAVE"] = "no-existe"
    caso("(c) Clave sin fila en el maestro: no cambia nada",
         negocio_mod._config_maestra() == {})
finally:
    sheets_mod.leer_pestana = orig_leer
    sheets_mod.leer_configuracion = orig_cfg_op
    os.environ.pop("NEGOCIOS_SHEET_ID", None)
    os.environ.pop("NEGOCIO_CLAVE", None)

# ---------- (d) Cortes en vivo ----------

# Paquete básico: el agente pide agendar, pero no se propone nada.
orig = _con_config({"paquete": "basico"})
try:
    d = Deps36(agente=RespuestaAgente(
        respuesta_texto="Perfecto, te agendo.", quiere_agendar="si",
        fecha_cita=FECHA_OK, motivo="Limpieza"))
    r = atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("(d) Paquete básico: sin propuesta con botones",
         not d.botones and not r.get("cita_propuesta") and bool(d.textos),
         f"botones={d.botones} r={r}")
finally:
    _sin_config(orig)

# Canal WhatsApp apagado: el robot no contesta.
orig = _con_config({"canal_whatsapp": "NO"})
try:
    d = Deps36()
    r = atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    caso("(d) Canal WhatsApp apagado: respondio=False, sin textos",
         r.get("respondio") is False and not d.textos, f"r={r}")
finally:
    _sin_config(orig)

# Reportes en básico: se omiten sin tocar la hoja.
orig = _con_config({"paquete": "basico"})
try:
    r1 = report_mod.generar_reporte_semanal()
    r2 = report_mod.generar_resumen_manana()
    caso("(d) Paquete básico: reporte semanal y resumen omitidos",
         r1.get("omitido") is True and r2.get("omitido") is True,
         f"r1={r1} r2={r2}")
finally:
    _sin_config(orig)

print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} pasaron")
if FALLOS:
    print("Fallaron:", ", ".join(FALLOS))
    sys.exit(1)
print("TODO VERDE en test_v3_6.py")
