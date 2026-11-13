"""Pruebas de la versión 2.10 (prompt comercial), SIN internet.

Cubre solo lo nuevo de la v2.10:
(a) el prompt tiene personaje: Ana, recepcionista, siempre a la orden.
(b) el prompt trae el método comercial en 3 pasos: Entiende, Responde,
    Avanza (y la regla de ofrecer la cita después de cada precio).
(c) el prompt prohíbe soltar el catálogo entero (máximo 3 servicios).
(d) el prompt prohíbe inventar: solo Conocimiento, palabra por palabra.
(e) de punta a punta: con una respuesta comercial del agente, el cliente
    recibe ese texto y la cita propuesta se guarda.

Uso:  python test_v2_10.py
"""

import json
from datetime import datetime, timezone

import robot.agent as agent_mod
import robot.logic as logic_mod
from robot.agent import preguntar_agente
from robot.logic import atender_mensaje

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV210:
    """Servicios de mentira."""

    def __init__(self, agente_json=None):
        self.agente_json = agente_json
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.botones_enviados = []
        self.citas = []
        self.llamadas_agente = []

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
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []

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
        return agent_mod.preguntar_agente(mensaje, conocimiento, fotos, historial)

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        cita = {"inicio": fecha_cita}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def enviar_botones(self, telefono, texto, botones):
        self.botones_enviados.append((telefono, texto, botones))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def main():
    prompts = []
    generar_viejo = agent_mod.generar_texto
    try:
        def generar_falso(prompt):
            prompts.append(prompt)
            return json.dumps({
                "respuesta_texto": "La limpieza cuesta $600, dura 60 minutos y no duele. "
                "¿Te la agendo para mañana a las 9:00? Ese horario está libre.",
                "quiere_agendar": "si", "necesita_handoff": "no",
                "motivo_handoff": "", "foto_oficial_url_or_null": "",
                "nombre": "Jose Ramon", "motivo": "Quiere una limpieza",
                "fecha_cita": "2026-11-16T09:00:00",
            })

        agent_mod.generar_texto = generar_falso
        r = preguntar_agente("¿cuánto cuesta la limpieza?", CONOCIMIENTO, FOTOS, [])
        prompt = prompts[0]

        caso("(a) El prompt tiene personaje: Ana, recepcionista, a la orden",
             "Te llamas Ana" in prompt and "recepcionista" in prompt
             and "a la orden" in prompt,
             f"prompt={prompt[:200]}")
        caso("(b) El prompt trae el método: Entiende, Responde, Avanza",
             "ENTIENDE" in prompt and "RESPONDE JUSTO LO QUE PREGUNTÓ" in prompt
             and "AVANZA" in prompt,
             "falta un paso del método")
        caso("(b) El prompt ordena ofrecer la cita después de cada precio",
             "¿Te la agendo" in prompt and "Ese horario está libre" in prompt)
        caso("(c) El prompt prohíbe el catálogo entero (máximo 3 servicios)",
             "catálogo entero" in prompt and "solo los 3 más pedidos" in prompt)
        caso("(d) El prompt prohíbe inventar: solo Conocimiento, palabra por palabra",
             "palabra por palabra" in prompt and "Déjame confirmarlo" in prompt
             and "Nunca inventes precios, descuentos, promociones" in prompt)
        caso("(e) El prompt sigue pidiendo solo JSON con los mismos campos",
             "ÚNICAMENTE con un JSON válido" in prompt
             and "respuesta_texto" in prompt and "fecha_cita" in prompt)

        # (e) De punta a punta: la respuesta comercial llega al cliente
        # y la propuesta se guarda.
        logic_mod._CITAS_PENDIENTES.clear()
        d = DepsV210()
        r2 = atender_mensaje(d, "5216694608263", "Jose Ramon",
                              "¿cuánto cuesta la limpieza?",
                              con_ritmo=False,
                              ahora=datetime(2026, 11, 13, 4, 30, tzinfo=timezone.utc))
        caso("(e) El cliente recibe la respuesta comercial del agente (con botones)",
             any("¿Te la agendo" in t for _, t, _ in d.botones_enviados),
             f"botones={d.botones_enviados}")
        caso("(e) La cita propuesta se guarda (lunes 09:00)",
             "5216694608263" in logic_mod._CITAS_PENDIENTES
             and logic_mod._CITAS_PENDIENTES["5216694608263"]["fecha_cita"].startswith("2026-11-16T09:00"),
             f"propuestas={logic_mod._CITAS_PENDIENTES}")
    finally:
        agent_mod.generar_texto = generar_viejo

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
