"""Pruebas de la versión 2.6 (la IA contesta siempre), SIN internet.

Cubre solo lo nuevo de la v2.6 (lo anterior sigue en test_simulado.py,
test_v2.py, test_v2_2.py, test_v2_3.py, test_v2_4.py y test_v2_5.py):
(a) el mensaje real de Jose de las 21:19 ("pero como sabes q es lo que
    quiero … no me ha calificado ni me ha saludado …") va AL AGENTE,
    nunca a la frase grabada.
(b) un "hola" de noche también va al agente, con contexto (fecha, hora,
    cerrado, próxima apertura, nombre del cliente).
(c) si Gemini falla de noche, el cliente recibe "dame un momento"
    honesto, no la frase grabada, y el dueño recibe la alerta.
(d) el contexto del agente siempre trae fecha, hora, abierto/cerrado
    y el nombre del cliente.
(e) el agente que propone una hora cerrada de noche se corrige a la
    próxima apertura (sigue funcionando tras quitar el atajo).

Uso:  python test_v2_6.py
"""

from datetime import datetime, timezone

import robot.logic as logic_mod
from robot.agent import RespuestaAgente
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


class DepsV26:
    """Servicios de mentira."""

    def __init__(self, agente=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Hola, Jose Ramon. Perdón por eso, tienes razón: déjame atenderte bien. ¿Qué necesitas?")
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.alertas_error = []
        self.llamadas_agente = []
        self.vistos = []

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
        self.alertas_error.append((motivo, telefono))


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


JUEVES_NOCHE = datetime(2026, 11, 13, 4, 19, tzinfo=timezone.utc)  # jueves 21:19 Mazatlán


def main():
    mensaje_jose = ("pero como sabes q es lo que quiero … no me ha calificado "
                    "ni me ha saludado … es usted un maleducado una ai sin cerebro")

    # (a) El mensaje real de Jose: va al agente, nunca a la plantilla.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV26()
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", mensaje_jose,
                         con_ritmo=False, ahora=JUEVES_NOCHE)
    caso("(a) El mensaje de Jose va al agente, no a la frase grabada",
         len(d.llamadas_agente) == 1
         and not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados),
         f"llamadas={len(d.llamadas_agente)} textos={d.textos_enviados}")
    caso("(a) El cliente recibe la respuesta del agente (con su nombre)",
         any("Jose Ramon" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (b) Un "hola" de noche también va al agente.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV26()
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "hola muy buenas noches",
                         con_ritmo=False, ahora=JUEVES_NOCHE)
    caso("(b) Un 'hola' de noche va al agente (ya no hay atajo de plantilla)",
         len(d.llamadas_agente) == 1
         and not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (c) Gemini falla de noche: "dame un momento" honesto + alerta al dueño.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_falla = RespuestaAgente.segura("Dame un momento, por favor.", falla_tecnica=True)
    d = DepsV26(agente=agente_falla)
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "Hola, quiero una cita",
                         con_ritmo=False, ahora=JUEVES_NOCHE)
    caso("(c) Gemini falla de noche: 'dame un momento', sin frase grabada",
         any("Dame un momento" in t for _, t in d.textos_enviados)
         and not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    caso("(c) Gemini falla: el dueño recibe la alerta de error",
         len(d.alertas_error) == 1, f"alertas_error={d.alertas_error}")

    # (d) El contexto del agente trae fecha, hora, cerrado y nombre.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV26()
    atender_mensaje(d, "5216694608263", "Jose Ramon", "Hola",
                     con_ritmo=False, ahora=JUEVES_NOCHE)
    contexto = d.llamadas_agente[0]
    caso("(d) El contexto trae fecha, hora, CERRADO, horarios y nombre",
         "jueves 12 de noviembre" in contexto and "21:19" in contexto
         and "CERRADO" in contexto and "09:00 a 18:00" in contexto
         and "Jose Ramon" in contexto,
         f"contexto={contexto[:200]}")

    # (e) Hora cerrada propuesta de noche: se corrige a la próxima apertura.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_mal_horario = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Jose Ramon", motivo="Quiere agendar",
        fecha_cita="2026-11-15T10:00:00", quiere_agendar="si")
    d = DepsV26(agente=agente_mal_horario)
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "Quiero cita el domingo a las 10",
                         con_ritmo=False, ahora=datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc))
    caso("(e) Hora cerrada de noche: se corrige a lunes 09:00",
         r.get("fecha_cita", "").startswith("2026-11-16T09:00"),
         f"r={r}")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
