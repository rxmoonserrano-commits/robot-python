"""Pruebas de la versión 2.11 (comercial voraz), SIN internet.

Cubre solo lo nuevo de la v2.11:
(a) el prompt ordena que cada respuesta acerque a la cita (beneficio,
    precio, cita) y termine con un paso concreto, no con una pregunta
    genérica.
(b) el prompt ordena ofrecer DOS opciones concretas de día y hora,
    nunca un sí o no.
(c) el prompt prohíbe terminar con "¿tienes alguna otra duda?" y
    "¿te gustaría saber más?".
(d) el prompt trae el guion para "lo voy a pensar": apartar el lugar
    hasta mañana sin compromiso, sin discutir ni bajar el precio.
(e) el prompt prohíbe rogar, repetir la pregunta, inventar urgencia
    y descuentos: solo la disponibilidad real.
(f) el prompt ordena calificar en la plática (qué le duele, desde
    cuándo, si ya se había atendido), máximo 3 preguntas.
(g) de punta a punta: con una respuesta voraz del agente, el cliente
    recibe ese texto con botones y la propuesta se guarda.

Uso:  python test_v2_11.py
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


class DepsV211:
    """Servicios de mentira."""

    def __init__(self):
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.botones_enviados = []
        self.citas = []

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
                "¿Te la agendo para mañana a las 9:00 o el sábado a las 10:00?",
                "quiere_agendar": "si", "necesita_handoff": "no",
                "motivo_handoff": "", "foto_oficial_url_or_null": "",
                "nombre": "Jose Ramon", "motivo": "Quiere una limpieza",
                "fecha_cita": "2026-11-16T09:00:00",
            })

        agent_mod.generar_texto = generar_falso
        preguntar_agente("¿cuánto cuesta la limpieza?", CONOCIMIENTO, FOTOS, [])
        prompt = " ".join(prompts[0].split())

        # (v2.13) "Cada respuesta acerca a la cita" ahora vive en la
        # decisión por etapa (pregunto), no en una sección aparte.
        caso("(a) Cada respuesta acerca a la cita: beneficio, precio, cita",
             "Beneficio primero" in prompt and "precio después, cita al final" in prompt
             and "DOS opciones concretas de día y hora" in prompt)
        caso("(b) Ofrece DOS opciones concretas de día y hora",
             "DOS opciones concretas de día y hora" in prompt
             and "para mañana a las 9:00 o el sábado a las 10:00?" in prompt)
        caso("(c) Prohíbe cerrar con preguntas genéricas",
             'Nunca termines con "¿tienes alguna otra duda?"' in prompt
             and 'ni "¿te gustaría saber' in prompt)
        caso("(d) Guion para 'lo voy a pensar': apartar el lugar hasta mañana",
             'lo voy a pensar' in prompt
             and "Te aparto el lugar hasta mañana sin compromiso" in prompt
             and "no bajes el precio" in prompt)
        caso("(e) Prohíbe inventar urgencia o descuentos y bajar el precio",
             "Nunca inventes urgencia ni descuentos" in prompt
             and "la urgencia es solo la disponibilidad real" in prompt
             and "No discutas, no bajes el precio" in prompt)
        caso("(f) Califica en la plática: qué le duele, desde cuándo, atendido antes",
             "pregúntale qué le duele, desde cuándo y si es urgente" in prompt
             and "máximo 3 preguntas, una a la vez" in prompt)
        caso("(g) El prompt sigue pidiendo solo JSON con los mismos campos",
             "ÚNICAMENTE con un JSON válido" in prompt
             and "respuesta_texto" in prompt and "fecha_cita" in prompt)

        # (g) De punta a punta: la respuesta voraz llega al cliente con
        # botones y la propuesta se guarda.
        logic_mod._CITAS_PENDIENTES.clear()
        d = DepsV211()
        atender_mensaje(d, "5216694608263", "Jose Ramon",
                        "¿cuánto cuesta la limpieza?",
                        con_ritmo=False,
                        ahora=datetime(2026, 11, 13, 4, 30, tzinfo=timezone.utc))
        caso("(g) El cliente recibe la oferta con dos opciones (botones)",
             any("mañana a las 9:00 o el sábado a las 10:00" in t
                 for _, t, _ in d.botones_enviados),
             f"botones={d.botones_enviados}")
        caso("(g) La cita propuesta se guarda (lunes 09:00)",
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
