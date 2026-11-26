"""Pruebas de la versión 2.4, SIN internet.

Cubre solo lo nuevo de la v2.4 (lo anterior sigue en test_simulado.py,
test_v2.py, test_v2_2.py y test_v2_3.py):
(a) de noche, "prefiero otra" con propuesta pendiente → no repite la
    frase grabada: borra la propuesta y pregunta por el nuevo día.
(b) de noche, "disculpe mejor no, si deseo cambiar la cita puedo?"
    con cita ya creada → borra el evento, limpia la hoja y pregunta
    por el nuevo día.
(c) de noche, "quiero cancelar mi cita" con cita creada → cancela
    y lo confirma.
(d) de noche, una pregunta normal ("¿cuánto cuesta la limpieza?")
    → se llama al AGENTE (no a la frase grabada) y se manda su texto.
(e) de noche, el agente propone una hora cerrada (domingo 10:00)
    → se corrige sola a la próxima apertura (lunes 09:00).
(f) de noche, si Gemini falla → respaldo con la frase grabada y la
    propuesta se guarda (no silencio).
(g) de día, cambiar con propuesta pendiente → pregunta por el nuevo día.
(h) _intencion_cambio: entiende "mejor no", "prefiero otra", "cancelar".

Uso:  python test_v2_4.py
"""

from datetime import datetime, timezone

import robot.logic as logic_mod
from robot.agent import RespuestaAgente
from robot.logic import _intencion_cambio, atender_mensaje

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV24:
    """Servicios de mentira, con cliente agendado y borrado de cita."""

    def __init__(self, agente=None, cliente=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.cliente = cliente
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.llamadas_agente = []
        self.vistos = []
        self.citas_canceladas = []
        self.clientes_cancelados = []

    def hora_libre(self, fecha_iso):
        # Agenda ficticia: en estos escenarios la hora está disponible.
        return True

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return self.cliente

    def cancelar_cita(self, telefono, fecha_cita):
        self.citas_canceladas.append((telefono, fecha_cita))
        return True

    def cancelar_cita_cliente(self, telefono):
        self.clientes_cancelados.append(telefono)

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
CLIENTE_AGENDADO = {"fecha": "2026-11-16T09:00:00-07:00", "nombre": "Jose Ramon",
                    "telefono": "5216694608263", "motivo": "Limpieza",
                    "fecha_cita": "2026-11-17T09:00:00-07:00",
                    "origen": "whatsapp", "estatus": "agendado", "handoff": "no"}
CLIENTE_PASADO = {"fecha": "2026-11-13T09:00:00-07:00", "nombre": "Jose Ramon",
                  "telefono": "5216694608263", "motivo": "Limpieza",
                  "fecha_cita": "2026-11-13T09:00:00-07:00",
                  "origen": "whatsapp", "estatus": "agendado", "handoff": "no"}


def main():
    # (a) "prefiero otra" de noche, con propuesta pendiente.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_agenda = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Ana", motivo="Quiere agendar",
        fecha_cita="2026-11-14T10:00:00", quiere_agendar="si")
    d = DepsV24(agente=agente_agenda)
    atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                     con_ritmo=False, ahora=LUNES_MANANA)
    assert "6671234567" in logic_mod._CITAS_PENDIENTES
    n_textos = len(d.textos_enviados)
    r = atender_mensaje(d, "6671234567", "Ana", "prefiero otra",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(a) 'prefiero otra' de noche: NO repite la frase grabada",
         not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados[n_textos:]),
         f"textos={d.textos_enviados}")
    caso("(a) 'prefiero otra': borra la propuesta y pregunta por el nuevo día",
         "6671234567" not in logic_mod._CITAS_PENDIENTES
         and any("Qué día y hora" in t for _, t in d.textos_enviados[n_textos:]),
         f"textos={d.textos_enviados}")

    # (b) El mensaje real de Jose: cambiar la cita ya creada.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV24(cliente=dict(CLIENTE_AGENDADO))
    r = atender_mensaje(d, "5216694608263", "Jose Ramon",
                         "disculpe mejor no, si deseo cambiar la cita puedo?",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(b) 'mejor no, ¿puedo cambiar la cita?': borra el evento de Calendar",
         len(d.citas_canceladas) == 1 and d.citas_canceladas[0][1].startswith("2026-11-17T09:00"),
         f"canceladas={d.citas_canceladas}")
    caso("(b) Cambiar cita: limpia la hoja y pregunta por el nuevo día",
         len(d.clientes_cancelados) == 1
         and any("cancelé tu cita" in t and "Qué día y hora" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    caso("(b) Cambiar cita: NO repite la frase grabada",
         not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados))

    # (c) Cancelar la cita creada.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV24(cliente=dict(CLIENTE_AGENDADO))
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "quiero cancelar mi cita",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(c) 'quiero cancelar mi cita': borra el evento y lo confirma",
         len(d.citas_canceladas) == 1
         and any("quedó cancelada" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (c2) Cancelar una cita que YA PASÓ: no se borra ningún evento
    # (ya terminó) y el robot dice la verdad: no hay cita vigente.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV24(cliente=dict(CLIENTE_PASADO))
    r = atender_mensaje(d, "5216694608263", "Jose Ramon", "quiero cancelar mi cita",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(c2) Cancelar cita pasada: no borra evento",
         len(d.citas_canceladas) == 0,
         f"canceladas={d.citas_canceladas}")
    caso("(c2) Cancelar cita pasada: dice que no hay cita vigente",
         any("No tienes ninguna cita agendada" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (d) Pregunta normal de noche: va al agente, no a la frase grabada.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_precio = RespuestaAgente(
        respuesta_texto="La limpieza cuesta $600 y dura 60 minutos. ¿Te agendo una?",
        nombre="", motivo="Preguntó por el precio de la limpieza")
    d = DepsV24(agente=agente_precio)
    r = atender_mensaje(d, "6671234567", "Ana", "¿cuánto cuesta la limpieza?",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(d) Pregunta de noche: se llama al agente (con contexto de cerrado)",
         len(d.llamadas_agente) == 1 and "CERRADO" in d.llamadas_agente[0],
         f"llamadas={d.llamadas_agente}")
    caso("(d) Pregunta de noche: se manda el texto del agente, no la frase grabada",
         any("La limpieza cuesta $600" in t for _, t in d.textos_enviados)
         and not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (e) El agente propone domingo 10:00 (cerrado): se corrige a lunes 09:00.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_mal_horario = RespuestaAgente(
        respuesta_texto="Perfecto.", nombre="Ana", motivo="Quiere agendar",
        fecha_cita="2026-11-15T10:00:00", quiere_agendar="si")
    d = DepsV24(agente=agente_mal_horario)
    r = atender_mensaje(d, "6671234567", "Ana", "Quiero cita el domingo a las 10",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(e) Hora cerrada propuesta por el agente: se corrige a lunes 09:00",
         r.get("fecha_cita", "").startswith("2026-11-16T09:00"),
         f"r={r}")
    caso("(e) La propuesta guardada también trae lunes 09:00",
         logic_mod._CITAS_PENDIENTES.get("6671234567", {}).get("fecha_cita", "").startswith("2026-11-16T09:00"),
         f"propuestas={logic_mod._CITAS_PENDIENTES}")

    # (f) Gemini falla de noche (v2.6): ya NO hay frase grabada de
    # respaldo. El cliente recibe un "dame un momento" honesto y no
    # se guarda ninguna propuesta inventada.
    logic_mod._CITAS_PENDIENTES.clear()
    agente_falla = RespuestaAgente.segura("Dame un momento, por favor.", falla_tecnica=True)
    d = DepsV24(agente=agente_falla)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola, quiero una cita",
                         con_ritmo=False, ahora=DOMINGO_NOCHE)
    caso("(f) Gemini falla de noche: 'dame un momento' honesto, sin frase grabada",
         r.get("handoff") is True and r.get("falla_tecnica") is True
         and any("Dame un momento" in t for _, t in d.textos_enviados)
         and not any("Ahora estamos cerrados" in t for _, t in d.textos_enviados)
         and "6671234567" not in logic_mod._CITAS_PENDIENTES,
         f"r={r} textos={d.textos_enviados}")

    # (g) De día, cambiar con propuesta pendiente.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsV24(agente=agente_agenda)
    atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                     con_ritmo=False, ahora=LUNES_MANANA)
    r = atender_mensaje(d, "6671234567", "Ana", "mejor no, quiero cambiarla",
                         con_ritmo=False, ahora=LUNES_MANANA)
    caso("(g) Cambiar de día: borra la propuesta y pregunta por el nuevo día",
         "6671234567" not in logic_mod._CITAS_PENDIENTES
         and any("Qué día y hora" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")

    # (h) La intención se entiende.
    caso("(h) _intencion_cambio entiende 'mejor no', 'prefiero otra', 'cancelar'",
         _intencion_cambio("disculpe mejor no, si deseo cambiar la cita puedo?") == "cambiar"
         and _intencion_cambio("prefiero otra", hay_propuesta=True) == "cambiar"
         and _intencion_cambio("quiero cancelar mi cita") == "cancelar"
         and _intencion_cambio("¿cuánto cuesta la limpieza?") is None
         and _intencion_cambio("otra", hay_propuesta=False) is None)

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
