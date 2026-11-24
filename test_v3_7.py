"""Pruebas de la v3.7 (alertas del dueño: 3 tipos, un correo semanal).

(a) El correo semanal trae los 3 tipos estilo "reporte de valor":
    citas confirmadas, necesitaron humano, clientes por recuperar
    (con borrador listo) + números que prueban el valor.
(b) Con alertas_instantaneas=NO, las alertas de cita y lead caliente
    NO salen al momento (van en el correo semanal); el handoff
    (necesita humano) sigue saliendo al momento por seguridad.
(c) Por defecto (sin configurar), las alertas al momento se mandan
    como siempre (compatibilidad).

Sin internet: todo con fakes y parches, como las demás pruebas.
"""

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import robot.logic as logic_mod
import robot.negocio as negocio_mod
import robot.report as report_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_boton, atender_mensaje

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


class Deps37:
    """Servicios de mentira con registro de alertas."""

    def __init__(self, agente=None):
        self.agente = agente or RespuestaAgente(respuesta_texto="Claro, te ayudo.")
        self.textos = []
        self.fotos_env = []
        self.botones = []
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.alertas_handoff = []
        self.alertas_cita = []
        self.alertas_lead = []
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
        cita = {"inicio": inicio.isoformat(), "fin": (inicio + timedelta(minutes=60)).isoformat()}
        self.citas.append(cita)
        return cita

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def proximos_huecos_libres(self, conocimiento, ahora):
        return []

    def hora_libre(self, fecha_iso):
        return True

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen="", hilo=""):
        self.alertas_handoff.append((nombre, telefono, motivo))

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_cita.append((nombre, telefono, motivo))

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas_lead.append((nombre, telefono, motivo))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


def agente_propone():
    return RespuestaAgente(
        respuesta_texto="Perfecto, te agendo.", quiere_agendar="si",
        fecha_cita=FECHA_OK, motivo="Limpieza", nombre="Ana")


def _con_config(cfg):
    orig = negocio_mod.configuracion
    negocio_mod.configuracion = lambda: dict(cfg)
    return orig


def _sin_config(orig):
    negocio_mod.configuracion = orig


# ---------- (a) Correo semanal de 3 tipos ----------

ahora = datetime.now(timezone.utc)
fecha = ahora.isoformat()
conv = [
    {"fecha": fecha, "telefono": "521", "quien_hablo": "cliente",
     "mensaje": "hola", "robot_respondio": "si", "motivo": ""},
    {"fecha": fecha, "telefono": "521", "quien_hablo": "robot",
     "mensaje": "hola", "robot_respondio": "si", "motivo": ""},
]
cli = [
    {"fecha": fecha, "nombre": "Ana", "telefono": "111", "motivo": "Limpieza",
     "fecha_cita": "2026-11-25T10:00:00", "origen": "whatsapp",
     "estatus": "agendado", "handoff": "no"},
    {"fecha": fecha, "nombre": "Beto", "telefono": "222", "motivo": "duda de pago",
     "fecha_cita": "", "origen": "whatsapp", "estatus": "en conversacion",
     "handoff": "si"},
    {"fecha": fecha, "nombre": "Carmen", "telefono": "333", "motivo": "blanqueamiento",
     "fecha_cita": "", "origen": "whatsapp", "estatus": "en conversacion",
     "handoff": "no"},
]
correos = []
guardados = []
orig_leer = report_mod.leer_pestana
orig_texto = report_mod.generar_texto
orig_correo = report_mod.enviar_correo
orig_guardar = report_mod.guardar_reporte
report_mod.leer_pestana = lambda tab: conv if tab == "Conversaciones" else cli
report_mod.generar_texto = lambda prompt, json_mode=True: "Esta semana atendimos bien."
report_mod.enviar_correo = lambda dest, asunto, cuerpo, html=None: correos.append((dest, asunto, cuerpo))
report_mod.guardar_reporte = lambda *args: guardados.append(args)
try:
    resultado = report_mod.generar_reporte_semanal()
finally:
    report_mod.leer_pestana = orig_leer
    report_mod.generar_texto = orig_texto
    report_mod.enviar_correo = orig_correo
    report_mod.guardar_reporte = orig_guardar

cuerpo = correos[0][2] if correos else ""
caso("(a) El correo trae los 3 tipos + números de valor",
     bool(correos)
     and "CITAS CONFIRMADAS (1)" in cuerpo and "Ana" in cuerpo
     and "NECESITARON ATENCIÓN HUMANA (1)" in cuerpo and "Beto" in cuerpo
     and "CLIENTES POR RECUPERAR (1)" in cuerpo and "Carmen" in cuerpo
     and "Borrador listo" in cuerpo
     and "TU SEMANA EN NÚMEROS" in cuerpo
     and "Tiempo ahorrado estimado" in cuerpo
     and "Esta semana atendimos bien." in cuerpo
     and "{" not in cuerpo,
     f"correo={cuerpo[:400]!r}")
caso("(a) El reporte se guarda en la hoja Reporte (misma forma)",
     bool(guardados) and guardados[0][3] == 1
     and resultado["mensajes_atendidos"] == 1,
     f"guardados={guardados} resultado={resultado}")

# ---------- (b) alertas_instantaneas=NO ----------

orig = _con_config({"alertas_instantaneas": "NO"})
try:
    logic_mod._CITAS_PENDIENTES.clear()
    d = Deps37(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("(b) NO: propuesta sale, pero sin alerta de lead al momento",
         len(d.botones) == 1 and d.alertas_lead == [],
         f"botones={d.botones} lead={d.alertas_lead}")
    atender_boton(d, TEL, "Ana", "confirmar_cita", con_ritmo=False, ahora=AHORA)
    caso("(b) NO: la cita se crea, pero sin alerta de cita al momento",
         len(d.citas) == 1 and d.alertas_cita == [],
         f"citas={d.citas} alertas={d.alertas_cita}")

    logic_mod._CITAS_PENDIENTES.clear()
    d2 = Deps37(agente=agente_propone())
    atender_mensaje(d2, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_boton(d2, TEL, "Ana", "hablar_persona", con_ritmo=False, ahora=AHORA)
    caso("(b) NO: el handoff (necesita humano) sigue saliendo al momento",
         len(d2.alertas_handoff) == 1,
         f"alertas={d2.alertas_handoff}")
finally:
    _sin_config(orig)

# ---------- (c) Por defecto: alertas al momento ----------

orig = _con_config({})
try:
    logic_mod._CITAS_PENDIENTES.clear()
    d3 = Deps37(agente=agente_propone())
    atender_mensaje(d3, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("(c) Por defecto: la alerta de lead caliente sí sale al momento",
         len(d3.alertas_lead) == 1, f"lead={d3.alertas_lead}")
finally:
    _sin_config(orig)

print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} pasaron")
if FALLOS:
    print("Fallaron:", ", ".join(FALLOS))
    sys.exit(1)
print("TODO VERDE en test_v3_7.py")
