"""Pruebas de la versión 2.12 (espera y no repetir), SIN internet.

Cubre solo lo nuevo de la v2.12:
(a) el prompt ordena leer todo el historial y contestar todo junto
    en una sola respuesta.
(b) el prompt prohíbe repetir la oferta si ya se ofreció en el último
    mensaje y el cliente aún no contestó.
(c) el prompt prohíbe ofrecer cita cuando el cliente solo saludó y
    aún no se sabe qué quiere: primero saluda y pregunta.
(d) el prompt ordena que de noche el negocio cerró y el robot atiende igual
    pero él atiende igual; nunca "ya cerramos" como si él cerrara.
(e) la espera para agrupar mensajes es 15 segundos (config, Agrupador
    y render.yaml).
(f) de punta a punta: un saludo simple recibe un saludo con pregunta,
    sin propuesta de cita.
(g) el prompt comercial voraz de la v2.11 sigue intacto (dos opciones,
    guion de "lo voy a pensar").

Uso:  python test_v2_12.py
"""

import json
import os
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


class DepsV212:
    """Servicios de mentira."""

    def __init__(self, agente_json=None):
        self.agente_json = agente_json
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
                "respuesta_texto": "¡Buenas noches, Jose Ramon! ¿En qué te puedo ayudar?",
                "quiere_agendar": "no", "necesita_handoff": "no",
                "motivo_handoff": "", "foto_oficial_url_or_null": "",
                "nombre": "Jose Ramon", "motivo": "",
                "fecha_cita": "",
            })

        agent_mod.generar_texto = generar_falso
        preguntar_agente("buenas noches", CONOCIMIENTO, FOTOS, [])
        prompt = " ".join(prompts[0].split())

        # (v2.13) El historial ya no se "lee": el estado llega calculado
        # por código en el bloque "[Estado del cliente]".
        caso("(a) El prompt usa el Estado del cliente, calculado por código",
             '"[Estado del cliente]"' in prompt and "Léelo primero" in prompt
             and "si ya le ofreciste una cita" in prompt)
        caso("(b) No repite la oferta si ya se ofreció y no contestaron",
             "ya le ofreciste una cita y no ha contestado" in prompt
             and "NO repitas la oferta" in prompt
             and "recuérdala en una frase corta" in prompt)
        caso("(c) Si solo saludó, no ofrece cita: saluda y pregunta",
             "el cliente solo saludó" in prompt
             and "NO ofrezcas cita todavía" in prompt
             and "pregúntale qué necesita" in prompt)
        caso("(d) De noche: el negocio cerró, el robot atiende igual",
             "el negocio está cerrado, tú no" in prompt
             and "El negocio ya cerró por hoy, pero yo te atiendo igual" in prompt
             and 'Nunca digas "ya cerramos"' in prompt)
        caso("(g) Lo voraz de la v2.11 sigue: dos opciones y 'lo voy a pensar'",
             "DOS opciones concretas de día y hora" in prompt
             and "Te aparto el lugar hasta mañana sin compromiso" in prompt)

        # (e) La espera es 15 segundos en los tres lugares.
        from robot.config import Settings
        import importlib
        import robot.agrupar as agrupar_mod
        importlib.reload(agrupar_mod)
        s = Settings()
        render = open(os.path.join(os.path.dirname(__file__), "render.yaml")).read()
        caso("(e) Espera de 15 s: config, Agrupador y render.yaml",
             s.espera_agrupar_segundos == 15
             and agrupar_mod.Agrupador.__init__.__defaults__ == (15.0, None, 300.0)
             and 'value: "15"' in render and "ESPERA_AGRUPAR_SEGUNDOS" in render,
             f"config={s.espera_agrupar_segundos}, defaults={agrupar_mod.Agrupador.__init__.__defaults__}")

        # (f) De punta a punta: un saludo recibe un saludo con pregunta,
        # sin propuesta de cita.
        logic_mod._CITAS_PENDIENTES.clear()
        d = DepsV212()
        atender_mensaje(d, "5216694608263", "Jose Ramon", "buenas noches",
                        con_ritmo=False,
                        ahora=datetime(2026, 11, 13, 5, 30, tzinfo=timezone.utc))
        caso("(f) Un saludo recibe saludo + pregunta, sin botones de cita",
             any("¿En qué te puedo ayudar?" in t for _, t in d.textos_enviados)
             and not d.botones_enviados and not logic_mod._CITAS_PENDIENTES,
             f"textos={d.textos_enviados}, botones={d.botones_enviados}")
    finally:
        agent_mod.generar_texto = generar_viejo

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
