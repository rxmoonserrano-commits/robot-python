"""Pruebas de la versión 2.3, SIN internet.

Cubre solo lo nuevo de la v2.3 (lo anterior sigue en test_simulado.py,
test_v2.py y test_v2_2.py):
(a) robot_activo = NO en Clientes → el robot no contesta, no marca
    visto, no llama al agente; solo registra el mensaje con "no".
(b) robot_activo en blanco o "SI" → contesta normal.
(c) el botón global (Control = NO) sigue mandando aunque el cliente
    esté en SI.
(d) el botón Confirmar con el cliente apagado → no crea la cita.
(e) "Hablar con una persona" con el cliente apagado → sí hace handoff
    (es el camino al humano, no una respuesta del robot).
(f) robot_activo_para_cliente: solo un NO explícito apaga.

Uso:  python test_v2_3.py
"""

from datetime import datetime, timezone

import robot.logic as logic_mod
from robot.agent import RespuestaAgente
from robot.logic import (
    atender_boton,
    atender_mensaje,
    robot_activo_para_cliente,
)

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Servicio 1",
     "respuesta_o_precio": "$500", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV23:
    """Servicios de mentira, con interruptor por cliente configurable."""

    def __init__(self, robot_activo="SI", control_activo="SI"):
        self.robot_activo = robot_activo
        self.control_activo = control_activo
        self.agente = RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.llamadas_agente = []
        self.vistos = []

    def leer_control(self):
        return {"bot_activo": self.control_activo, "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return self.robot_activo

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

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        cita = {"inicio": fecha_cita}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
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


def main():
    lunes_manana = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)

    # (a) Cliente apagado: silencio total, solo registro.
    d = DepsV23(robot_activo="NO")
    r = atender_mensaje(d, "6671234567", "Ana", "Hola, quiero una cita",
                         con_ritmo=False, ahora=lunes_manana)
    caso("(a) Cliente en NO: no responde",
         r.get("respondio") is False and r.get("motivo") == "robot apagado para este cliente",
         f"r={r}")
    caso("(a) Cliente en NO: no marca visto ni llama al agente ni manda texto",
         len(d.vistos) == 0 and len(d.llamadas_agente) == 0 and len(d.textos_enviados) == 0)
    caso("(a) Cliente en NO: el mensaje sí queda registrado con 'no'",
         len(d.conversaciones) == 1 and d.conversaciones[0]["robot_respondio"] == "no"
         and d.conversaciones[0]["motivo"] == "robot apagado para este cliente",
         f"conv={d.conversaciones}")

    # (b) Cliente en blanco / SI: contesta normal.
    for valor in ("", "SI", "si"):
        d = DepsV23(robot_activo=valor)
        r = atender_mensaje(d, "6671234567", "Ana", "Hola",
                             con_ritmo=False, ahora=lunes_manana)
        caso(f"(b) Cliente en '{valor or 'blanco'}': contesta normal",
             r.get("respondio") is True and len(d.textos_enviados) == 1,
             f"r={r}")

    # (c) El botón global sigue mandando.
    d = DepsV23(robot_activo="SI", control_activo="NO")
    r = atender_mensaje(d, "6671234567", "Ana", "Hola",
                         con_ritmo=False, ahora=lunes_manana)
    caso("(c) Control en NO: no responde aunque el cliente esté en SI",
         r.get("respondio") is False and r.get("motivo") == "boton apagado",
         f"r={r}")

    # (d) Botón Confirmar con el cliente apagado: no crea la cita.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_agenda = RespuestaAgente(
        respuesta_texto="Perfecto, Ana.", nombre="Ana",
        motivo="Quiere agendar una cita",
        fecha_cita="2026-11-14T10:00:00", quiere_agendar="si")
    d = DepsV23(robot_activo="SI")
    d.agente = agente_agenda
    atender_mensaje(d, "6671234567", "Ana", "Quiero cita",
                     con_ritmo=False, ahora=lunes_manana)
    d.robot_activo = "NO"  # el dueño lo apaga antes de que confirme
    r = atender_boton(d, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("(d) Confirmar con cliente en NO: no crea la cita",
         len(d.citas) == 0 and r.get("respondio") is False,
         f"r={r} citas={d.citas}")

    # (e) Hablar con una persona con el cliente apagado: sí hace handoff.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV23(robot_activo="NO")
    r = atender_boton(d, "6671234567", "Ana", "hablar_persona", con_ritmo=False)
    caso("(e) Hablar con persona con cliente en NO: sí pasa al humano",
         r.get("handoff") is True and len(d.alertas) == 1,
         f"r={r} alertas={d.alertas}")

    # (f) La regla pura: solo NO apaga.
    caso("(f) robot_activo_para_cliente: 'NO' apaga, 'no' apaga, '' no apaga, 'SI' no apaga",
         robot_activo_para_cliente("NO") is False
         and robot_activo_para_cliente("no") is False
         and robot_activo_para_cliente("") is True
         and robot_activo_para_cliente("SI") is True
         and robot_activo_para_cliente("cualquier cosa") is True)

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
