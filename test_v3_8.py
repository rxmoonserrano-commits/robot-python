"""Pruebas de la versión 3.8, SIN internet.

IA apagada por cliente (robot_activo = NO) y la mecánica de Handoff:
(a) Urgencia con la IA apagada → correo al dueño (handoff), sin
    responderle al paciente, caso marcado en Clientes.
(b) Queja con la IA apagada → igual: alerta por correo.
(c) Pedido explícito de persona con la IA apagada → igual: alerta.
(d) Duda normal con la IA apagada → solo registro, SIN alerta
    (decisión: "alerta solo en casos graves").
(e) "¿La limpieza duele?" con la IA apagada → NO es urgencia
    (pregunta, no dice que le duela) → sin alerta.
(f) Botón global (Control) apagado → también alerta en casos graves;
    dudas normales solo se registran (mismo criterio que por chat).
(g) IA encendida + duda normal → contesta normal y sin alerta
    (regresión: nada de esto cambia el camino de siempre).
(h) Reglas puras de _motivo_handoff_en_silencio.

Uso:  python test_v3_8.py
"""

from datetime import datetime, timezone

from robot.agent import RespuestaAgente
from robot.logic import (
    _motivo_handoff_en_silencio,
    atender_boton,
    atender_mensaje,
)

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
     "respuesta_o_precio": "$500", "detalle": "Dura 45 minutos"},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto.jpg"}]


class DepsV38:
    """Servicios de mentira: guardan todo en memoria."""

    def __init__(self, robot_activo="NO", control_activo="SI"):
        self.robot_activo = robot_activo
        self.control_activo = control_activo
        self.agente = RespuestaAgente(
            respuesta_texto="Claro. La limpieza cuesta $500. ¿Qué día te viene mejor?")
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
        self.conversaciones.append({"fecha": fecha, "telefono": telefono,
                                    "quien_hablo": quien, "mensaje": mensaje,
                                    "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita,
                              "origen": origen, "estatus": estatus, "handoff": handoff})

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

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen=""):
        self.alertas.append((nombre, telefono, motivo, ultimo_mensaje))

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
    ahora = datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
    tel = "6671234567"

    # (a) Urgencia con la IA apagada → alerta, sin responder.
    d = DepsV38(robot_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "Me duele muchísimo la muela, es urgente",
                        con_ritmo=False, ahora=ahora)
    caso("(a) Urgencia con IA apagada: no le responde al paciente",
         r.get("respondio") is False and not d.textos_enviados and not d.vistos,
         f"r={r}")
    caso("(a) Urgencia con IA apagada: SÍ manda la alerta de handoff",
         len(d.alertas) == 1 and "Urgencia" in d.alertas[0][2],
         f"alertas={d.alertas}")
    caso("(a) Urgencia con IA apagada: caso marcado en Clientes (handoff=si)",
         len(d.clientes) == 1 and d.clientes[0]["handoff"] == "si",
         f"clientes={d.clientes}")
    caso("(a) Urgencia con IA apagada: el mensaje queda registrado como 'no'",
         len(d.conversaciones) == 1 and d.conversaciones[0]["robot_respondio"] == "no"
         and d.conversaciones[0]["motivo"] == "robot apagado para este cliente",
         f"conv={d.conversaciones}")
    caso("(a) Urgencia con IA apagada: motivo del resultado dice handoff alertado",
         r.get("handoff") is True and "handoff alertado" in str(r.get("motivo")),
         f"r={r}")

    # (b) Queja con la IA apagada → alerta.
    d = DepsV38(robot_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "Una queja: tardaron una hora en atenderme, pésimo servicio",
                        con_ritmo=False, ahora=ahora)
    caso("(b) Queja con IA apagada: alerta por correo",
         len(d.alertas) == 1 and "Queja" in d.alertas[0][2] and r.get("handoff") is True,
         f"alertas={d.alertas} r={r}")
    caso("(b) Queja con IA apagada: sin respuesta al paciente",
         not d.textos_enviados and r.get("respondio") is False)

    # (c) Pide a una persona con la IA apagada → alerta.
    d = DepsV38(robot_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "Quiero hablar con una persona, por favor",
                        con_ritmo=False, ahora=ahora)
    caso("(c) Pide persona con IA apagada: alerta por correo",
         len(d.alertas) == 1 and "persona" in d.alertas[0][2] and r.get("handoff") is True,
         f"alertas={d.alertas} r={r}")

    # (d) Duda normal con la IA apagada → solo registro, SIN alerta.
    d = DepsV38(robot_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "¿Cuánto cuesta una limpieza?",
                        con_ritmo=False, ahora=ahora)
    caso("(d) Duda normal con IA apagada: solo registro, sin alerta",
         r.get("respondio") is False and r.get("handoff") is False
         and not d.alertas and not d.textos_enviados,
         f"r={r} alertas={d.alertas}")
    caso("(d) Duda normal con IA apagada: motivo original intacto",
         r.get("motivo") == "robot apagado para este cliente"
         and len(d.conversaciones) == 1
         and d.conversaciones[0]["motivo"] == "robot apagado para este cliente",
         f"r={r}")

    # (e) "¿La limpieza duele?" NO es urgencia (pregunta, no padecimiento).
    d = DepsV38(robot_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "¿La limpieza duele? Tengo miedo",
                        con_ritmo=False, ahora=ahora)
    caso("(e) Pregunta sobre dolor con IA apagada: no es urgencia, sin alerta",
         not d.alertas and r.get("handoff") is False,
         f"alertas={d.alertas} r={r}")

    # (f) Botón global apagado: alerta en casos graves, como por chat.
    d = DepsV38(robot_activo="SI", control_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "Es urgente, me duele",
                        con_ritmo=False, ahora=ahora)
    caso("(f) Control global NO + urgencia: alerta por correo",
         len(d.alertas) == 1 and r.get("handoff") is True and not d.textos_enviados,
         f"r={r} alertas={d.alertas}")
    caso("(f) Control global NO + urgencia: el mensaje queda registrado como 'boton apagado'",
         len(d.conversaciones) == 1
         and d.conversaciones[0]["motivo"] == "boton apagado",
         f"conv={d.conversaciones}")

    # (f2) Botón global apagado + duda normal → solo registro.
    d = DepsV38(robot_activo="SI", control_activo="NO")
    r = atender_mensaje(d, tel, "Ana", "¿Cuánto cuesta una limpieza?",
                        con_ritmo=False, ahora=ahora)
    caso("(f2) Control global NO + duda: solo registro, sin alerta",
         not d.alertas and r.get("motivo") == "boton apagado"
         and r.get("handoff") is False,
         f"r={r} alertas={d.alertas}")

    # (g) IA encendida + duda normal: contesta normal (regresión).
    d = DepsV38(robot_activo="SI")
    r = atender_mensaje(d, tel, "Ana", "¿Cuánto cuesta una limpieza?",
                        con_ritmo=False, ahora=ahora)
    caso("(g) IA encendida + duda: contesta normal y sin alerta",
         r.get("respondio") is True and len(d.textos_enviados) == 1 and not d.alertas,
         f"r={r} textos={d.textos_enviados}")

    # (h) Reglas puras.
    caso("(h) _motivo_handoff_en_silencio: urgencia → motivo",
         "Urgencia" in _motivo_handoff_en_silencio("URGENTE, ya"))
    caso("(h) _motivo_handoff_en_silencio: queja con acentos → motivo",
         "Queja" in _motivo_handoff_en_silencio("¡Reclamación! Pésimo"))
    caso("(h) _motivo_handoff_en_silencio: pedir persona → motivo",
         "persona" in _motivo_handoff_en_silencio("Necesito hablar con alguien"))
    caso("(h) _motivo_handoff_en_silencio: duda normal → vacío",
         _motivo_handoff_en_silencio("¿Tienen horario el sábado?") == "")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
