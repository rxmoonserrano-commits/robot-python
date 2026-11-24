"""Pruebas de la versión 2.5 (24/7 de verdad), SIN internet.

Cubre solo lo nuevo de la v2.5 (lo anterior sigue en test_simulado.py,
test_v2.py, test_v2_2.py, test_v2_3.py y test_v2_4.py):
(a) una propuesta de noche se guarda en la hoja (guardar_propuesta),
    no solo en memoria.
(b) al confirmar con el botón, la propuesta se borra de la hoja.
(c) cargar_propuestas recupera las propuestas guardadas al arrancar.
(d) de noche, un mensaje sin nombre ni motivo igual registra el lead.
(e) de día, un saludo sin nombre ni motivo NO registra al cliente
    (la regla de siempre se mantiene de día).
(f) Gemini reintenta una vez si responde 429 y luego tiene éxito.
(g) al cambiar una cita, la propuesta se borra de la hoja.

Uso:  python test_v2_5.py
"""

from datetime import datetime, timezone

import robot.gemini as gemini_mod
import robot.logic as logic_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_boton, atender_mensaje, cargar_propuestas

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV25:
    """Servicios de mentira, con propuestas guardadas 'en la hoja'."""

    def __init__(self, agente=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.llamadas_agente = []
        self.vistos = []
        self.propuestas_hoja = {}

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return None

    def cancelar_cita(self, telefono, fecha_cita):
        return False

    def cancelar_cita_cliente(self, telefono):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        self.propuestas_hoja[telefono] = dict(propuesta)

    def borrar_propuesta(self, telefono):
        self.propuestas_hoja.pop(telefono, None)

    def leer_propuestas(self):
        return [{"telefono": t, **p} for t, p in self.propuestas_hoja.items()]

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return FOTOS

    def leer_historial(self, telefono):
        return [c for c in self.conversaciones if c["telefono"] == telefono]

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
                                    "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp",
                          estatus="en conversacion", handoff="no"):
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita, "origen": origen,
                              "estatus": estatus, "handoff": handoff})

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.llamadas_agente.append(mensaje)
        return self.agente

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        cita = {"inicio": fecha_cita}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen="", hilo=""):
        self.alertas.append((nombre, telefono, motivo))

    def marcar_leido_y_escribiendo(self, message_id):
        self.vistos.append(message_id)

    def enviar_botones(self, telefono, texto, botones):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


DOMINGO_NOCHE = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)   # domingo 20:00 Mazatlán
LUNES_MANANA = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)  # lunes 10:00 Mazatlán


def main():
    # (a) Propuesta de noche: la crea el agente (lunes 09:00) y se
    # guarda en la hoja, no solo en memoria.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_lunes = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Ana", motivo="Quiere agendar",
        fecha_cita="2026-11-16T09:00:00", quiere_agendar="si")
    d = DepsV25(agente=agente_lunes)
    r = atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(a) Propuesta de noche: se guarda en la hoja",
         "6671234567" in d.propuestas_hoja
         and d.propuestas_hoja["6671234567"]["fecha_cita"].startswith("2026-11-16T09:00"),
         f"hoja={d.propuestas_hoja}")
    caso("(a) Propuesta de noche: también queda en memoria",
         "6671234567" in logic_mod._CITAS_PENDIENTES)

    # (b) Confirmar con el botón: borra la propuesta de la hoja y crea la cita.
    r = atender_boton(d, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("(b) Confirmar: borra la propuesta de la hoja y crea la cita",
         "6671234567" not in d.propuestas_hoja and len(d.citas) == 1,
         f"hoja={d.propuestas_hoja} citas={d.citas}")

    # (c) cargar_propuestas: al arrancar, se recuperan de la hoja.
    logic_mod._CITAS_PENDIENTES.clear()
    d2 = DepsV25()
    d2.propuestas_hoja["6671234567"] = {
        "nombre": "Ana", "motivo": "Quiere agendar",
        "fecha_cita": "2026-11-16T09:00:00-07:00",
        "fecha_bonita": "lunes 16 de noviembre a las 09:00",
        "creado_en": "2026-11-16T03:00:00+00:00",
    }
    n = cargar_propuestas(d2)
    caso("(c) cargar_propuestas: recupera 1 propuesta al arrancar",
         n == 1 and "6671234567" in logic_mod._CITAS_PENDIENTES
         and logic_mod._CITAS_PENDIENTES["6671234567"]["fecha_cita"].startswith("2026-11-16T09:00"),
         f"n={n} memoria={logic_mod._CITAS_PENDIENTES}")
    r = atender_boton(d2, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("(c) Tras recuperar, el botón Confirmar sí crea la cita",
         len(d2.citas) == 1, f"r={r} citas={d2.citas}")

    # (d) De noche, sin nombre ni motivo: igual queda el lead.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_sin_datos = RespuestaAgente(respuesta_texto="Hola, ¿en qué te ayudo?")
    d = DepsV25(agente=agente_sin_datos)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola, ¿cuánto cuesta la limpieza?",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(d) De noche sin nombre ni motivo: el lead queda registrado",
         len(d.clientes) == 1 and d.clientes[0]["telefono"] == "6671234567"
         and "limpieza" in d.clientes[0]["motivo"].lower(),
         f"clientes={d.clientes}")

    # (e) De día, sin nombre ni motivo: NO se registra (regla de siempre).
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV25(agente=agente_sin_datos)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola",
                         con_ritmo=False, ahora=LUNES_MANANA)
    caso("(e) De día sin nombre ni motivo: no se registra al cliente",
         len(d.clientes) == 0, f"clientes={d.clientes}")

    # (f) Gemini: 429 una vez, luego 200 → reintenta y tiene éxito.
    llamadas = {"n": 0}

    class Resp:
        def __init__(self, status, texto=""):
            self.status_code = status
            self.text = texto

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "hola, soy Gemini"}]}}]}

    real_post = gemini_mod.requests.post
    real_sleep = gemini_mod.time.sleep
    real_key = gemini_mod.settings.gemini_api_key
    try:
        gemini_mod.settings.gemini_api_key = "clave-de-prueba"
        def post_falso(url, json=None, timeout=None):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                return Resp(429, "cuota por minuto")
            return Resp(200)
        gemini_mod.requests.post = post_falso
        gemini_mod.time.sleep = lambda s: None
        texto = gemini_mod.generar_texto("Hola")
        caso("(f) Gemini 429 y luego 200: reintenta una vez y tiene éxito",
             texto == "hola, soy Gemini" and llamadas["n"] == 2,
             f"texto={texto} llamadas={llamadas['n']}")
    finally:
        gemini_mod.requests.post = real_post
        gemini_mod.time.sleep = real_sleep
        gemini_mod.settings.gemini_api_key = real_key

    # (g) Cambiar una cita borra la propuesta de la hoja.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_agenda = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Ana", motivo="Quiere agendar",
        fecha_cita="2026-11-16T10:00:00", quiere_agendar="si")
    d = DepsV25(agente=agente_agenda)
    atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                     con_ritmo=False, ahora=LUNES_MANANA)
    assert "6671234567" in d.propuestas_hoja
    r = atender_mensaje(d, "6671234567", "Ana", "mejor no, quiero cambiarla",
                         con_ritmo=False, ahora=LUNES_MANANA)
    caso("(g) Cambiar cita: borra la propuesta de la hoja",
         "6671234567" not in d.propuestas_hoja
         and "6671234567" not in logic_mod._CITAS_PENDIENTES,
         f"hoja={d.propuestas_hoja}")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
