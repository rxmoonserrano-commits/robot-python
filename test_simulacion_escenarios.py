"""Simulación de escenarios contra el código REAL (solo lectura).

Jose pidió simular muchos escenarios para saber cómo actúa el
robot y por qué "???" responde "¡Gracias! ¿En qué te ayudo hoy?".
Este archivo NO modifica el robot: corre `atender_mensaje` con
dependencias falsas (como las pruebas) y reporta qué haría el
robot en cada escenario: motivo interno + respuesta + botones.

Uso: python3 test_simulacion_escenarios.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import (  # noqa: E402
    Dependencias,
    _CITAS_PENDIENTES,
    _RETOMAR,
    atender_boton,
    atender_mensaje,
)

TEL = "5216694608263"
AHORA = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)  # domingo, fuera de horario
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()


class DepsSim(Dependencias):
    """Falso configurable: espejo, huecos, agente encolado."""

    def __init__(self, huecos=None, espejo=None, agente_cola=None, cliente=None,
                 historial=None):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []
        self.conversaciones = []
        self.citas = []
        self.citas_canceladas = []
        self.alertas_handoff = []
        self.alertas_urgentes = []
        self.alertas_confirmadas = []
        self.mensajes_al_agente = []
        self.huecos = huecos if huecos is not None else [LUNES, MARTES]
        self.espejo = espejo if espejo is not None else []
        self.cliente = cliente
        self.historial = historial if historial is not None else []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_al_agente.append(mensaje)
        if self.agente_cola:
            return self.agente_cola.pop(0)
        if "[URGENTE]" in mensaje:
            return RespuestaAgente(respuesta_texto=(
                "Ay, qué mal rato, lo siento mucho. Te paso con una persona "
                "de inmediato para que te atiendan lo antes posible."))
        return RespuestaAgente(respuesta_texto="Claro, te ayudo con eso.")

    def proximos_huecos_libres(self, conocimiento, ahora, cantidad=2, dias=3):
        return list(self.huecos)

    def proximos_huecos_profesionales(self, conocimiento, ahora, cantidad=2, dias=3):
        return []

    def duracion_servicio(self, motivo):
        return None

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        cita = {"nombre": nombre, "telefono": telefono, "motivo": motivo,
                "fecha_cita": fecha_cita, "nota": nota}
        self.citas.append(cita)
        return cita

    def registrar_cita_espejo(self, fila):
        pass

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None,
                               recordatorio_enviado=None, urgencia=None,
                               nueva_fecha=None, nueva_hora_inicio=None,
                               nueva_hora_fin=None):
        pass

    def leer_citas_espejo(self):
        return list(self.espejo)

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_confirmadas.append(motivo)

    def alerta_cita_urgente(self, nombre, telefono, motivo, fecha_bonita, fecha, razon=""):
        self.alertas_urgentes.append(razon)

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha, resumen="", hilo=""):
        self.alertas_handoff.append(motivo)

    def cancelar_cita(self, telefono, fecha_cita):
        self.citas_canceladas.append(fecha_cita)
        return True

    def cancelar_cita_cliente(self, telefono):
        pass

    def enviar_texto(self, telefono, texto):
        self.textos.append(texto)

    def enviar_botones(self, telefono, texto, botones):
        self.botones.append((texto, botones))

    def enviar_foto(self, telefono, url):
        pass

    def registrar_conversacion(self, fecha, telefono, quien, texto, respondio, motivo):
        self.conversaciones.append({"quien": quien, "texto": texto, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        pass

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        pass

    def leer_cliente(self, telefono):
        return self.cliente

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_conocimiento(self):
        return []

    def leer_fotos_oficiales(self):
        return []

    def leer_historial(self, telefono):
        return list(self.historial)

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []


def espejo_dos_citas():
    """El estado real de Jose: su cita del martes + la de su hermana."""
    return [
        {"ID_Cita": "C-1", "Teléfono": TEL, "Servicio": "Blanqueamiento dental",
         "Fecha": "2026-11-24", "Hora_inicio": "09:00", "Hora_fin": "10:00",
         "Estado": "Confirmada", "Notas": "Paciente: Jose Ramon Serrano Sopeña",
         "Urgencia": "NO"},
        {"ID_Cita": "C-2", "Teléfono": TEL, "Servicio": "Blanqueamiento dental",
         "Fecha": "2026-11-25", "Hora_inicio": "09:00", "Hora_fin": "10:00",
         "Estado": "Confirmada", "Notas": "Paciente: su hermana",
         "Urgencia": "NO"},
    ]


def propuesta_pendiente():
    """Una propuesta viva, como la que dejó la urgencia de las 11:36pm."""
    return {
        "nombre": "Jose Ramon",
        "motivo": "me duele es urgente",
        "fecha_cita": LUNES,
        "fecha_bonita": "lunes 23 de noviembre a las 09:00",
        "creado_en": (AHORA - timedelta(hours=1)).isoformat(),
        "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "", "numero_paciente": "",
        "cita2": None, "urgencia": "Urgencia del cliente: me duele es urgente",
    }


RESULTADOS = []


def escenario(nombre, mensaje, d, semilla_propuesta=False, boton=None):
    limpiar()
    if semilla_propuesta:
        _CITAS_PENDIENTES[TEL] = propuesta_pendiente()
    if boton:
        r = atender_boton(d, TEL, "Jose Ramon", boton, con_ritmo=False, ahora=AHORA)
    else:
        r = atender_mensaje(d, TEL, "Jose Ramon", mensaje, con_ritmo=False, ahora=AHORA)
    motivo = r.get("motivo", "?")
    respuesta = d.textos[-1] if d.textos else "(sin texto)"
    botones = ""
    if d.botones:
        botones = " | botones: " + ",".join(b[0] for b in d.botones[-1][1])
    RESULTADOS.append((nombre, mensaje, motivo, respuesta, botones))
    limpiar()


def main():
    # ---- Grupo A: propuesta pendiente + mensajes cortos (el bug) ----
    escenario("A1 propuesta + 'me duele es urgente'",
              "me duele es urgente", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("A2 propuesta + 'me urge una cita'",
              "me urge una cita", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("A3 propuesta + 'me puedes ayudar'",
              "me puedes ayudar", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("A4 propuesta + 'me va' (sí intencional)",
              "me va", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("A5 propuesta + 'sí' (sí intencional)",
              "sí", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("A6 propuesta + '👍' (sí intencional)",
              "👍", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)

    # ---- Grupo B: urgencia sin propuesta ----
    escenario("B1 urgencia, 2 citas (la suya + hermana)",
              "me duele es urgente", DepsSim(espejo=espejo_dos_citas()))
    escenario("B2 urgencia, sin citas",
              "me duele es urgente", DepsSim(espejo=[]))
    escenario("B3 urgencia, cita ya en la primera hora",
              "me duele es urgente",
              DepsSim(espejo=[{"ID_Cita": "C-1", "Teléfono": TEL,
                                "Servicio": "Blanqueamiento dental",
                                "Fecha": "2026-11-23", "Hora_inicio": "09:00",
                                "Hora_fin": "10:00", "Estado": "Confirmada",
                                "Notas": "Paciente: Jose Ramon Serrano Sopeña",
                                "Urgencia": "NO"}]))
    escenario("B4 'me duele mucho' (sin palabra urgente)",
              "me duele mucho la muela", DepsSim(espejo=[]))
    escenario("B5 '¿duele la limpieza?' (pregunta, no urgencia)",
              "¿duele la limpieza?", DepsSim(espejo=[]))

    # ---- Grupo C: símbolos y ruido ----
    escenario("C1 '???' sin propuesta", "???", DepsSim(espejo=[]))
    escenario("C2 '???' con propuesta", "???", DepsSim(espejo=[]),
              semilla_propuesta=True)
    escenario("C3 '😀😀' sin propuesta", "😀😀", DepsSim(espejo=[]))
    escenario("C4 'ok' sin propuesta", "ok", DepsSim(espejo=[]))

    # ---- Grupo D: tope de citas (flujo normal) ----
    agente_agendar = [RespuestaAgente(
        respuesta_texto="Te propongo tu cita.",
        quiere_agendar="si", fecha_cita=LUNES,
        motivo="Blanqueamiento dental")]
    escenario("D1 2 citas + 'quiero agendar mañana'",
              "quiero agendar mañana",
              DepsSim(espejo=espejo_dos_citas(), agente_cola=list(agente_agendar)))
    escenario("D2 1 cita + 'quiero agendar mañana'",
              "quiero agendar mañana",
              DepsSim(espejo=espejo_dos_citas()[:1], agente_cola=list(agente_agendar)))
    escenario("D3 0 citas + 'quiero agendar mañana'",
              "quiero agendar mañana",
              DepsSim(espejo=[], agente_cola=list(agente_agendar)))

    # ---- Grupo E: cambiar / cancelar / no ----
    escenario("E1 propuesta + 'no'", "no", DepsSim(espejo=[]),
              semilla_propuesta=True)
    escenario("E2 'quiero cambiar mi cita' con cita agendada",
              "quiero cambiar mi cita",
              DepsSim(espejo=espejo_dos_citas()[:1],
                      cliente={"estatus": "agendado", "fecha_cita": MARTES,
                               "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"}))
    escenario("E3 'quiero cancelar' con cita agendada",
              "quiero cancelar",
              DepsSim(espejo=espejo_dos_citas()[:1],
                      cliente={"estatus": "agendado", "fecha_cita": MARTES,
                               "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"}))

    # ---- Grupo F: varios ----
    escenario("F1 'hola'", "hola", DepsSim(espejo=[]))
    escenario("F2 'cuánto cuesta la limpieza'", "cuánto cuesta la limpieza",
              DepsSim(espejo=[]))
    escenario("F3 'quiero hablar con una persona'",
              "quiero hablar con una persona", DepsSim(espejo=[]))
    escenario("F4 botón 'adelantar_cita' con propuesta de adelanto",
              "", DepsSim(espejo=[]), boton="adelantar_cita")
    escenario("F5 botón 'dejar_cita_igual' con propuesta de adelanto",
              "", DepsSim(espejo=[]), boton="dejar_cita_igual")

    # ---- Grupo G: caza de fricciones (v3.16) ----
    escenario("G1 'no me duele nada' (NO es urgencia)",
              "no me duele nada, solo quiero info",
              DepsSim(espejo=[]))
    escenario("G2 'no es urgente, quiero agendar' (NO es urgencia)",
              "no es urgente, solo quiero agendar",
              DepsSim(espejo=[]))
    escenario("G3 'no quiero cancelar' con cita (NO cancela)",
              "no quiero cancelar",
              DepsSim(espejo=espejo_dos_citas()[:1],
                      cliente={"estatus": "agendado", "fecha_cita": MARTES,
                               "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"}))
    escenario("G4 'no quiero cambiar' con cita (NO cambia)",
              "no quiero cambiar",
              DepsSim(espejo=espejo_dos_citas()[:1],
                      cliente={"estatus": "agendado", "fecha_cita": MARTES,
                               "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"}))
    escenario("G5 'quiero cancelar' de verdad (sí cancela)",
              "quiero cancelar",
              DepsSim(espejo=espejo_dos_citas()[:1],
                      cliente={"estatus": "agendado", "fecha_cita": MARTES,
                               "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"}))
    escenario("G6 propuesta + 'me urge una cita' (NO confirma)",
              "me urge una cita", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("G7 propuesta + 'me puedes ayudar' (NO confirma)",
              "me puedes ayudar", DepsSim(espejo=espejo_dos_citas()),
              semilla_propuesta=True)
    escenario("G8 'gracias, ya no' (la IA cierra: terminar)",
              "gracias, ya no",
              DepsSim(espejo=[], agente_cola=[RespuestaAgente(
                  respuesta_texto="Quedamos a tus órdenes.",
                  accion="terminar", resumen_cliente="Preguntó precios.")]))
    escenario("G9 spam (la IA calla: no_responder)",
              "compra mi curso de trading",
              DepsSim(espejo=[], agente_cola=[RespuestaAgente(
                  respuesta_texto="", accion="no_responder")]))
    escenario("G10 'asdfgh' (texto sin sentido: va a la IA)",
              "asdfgh", DepsSim(espejo=[]))
    escenario("G11 pregunta tras 5 días (contexto con tiempo)",
              "¿y el blanqueamiento?",
              DepsSim(espejo=[], historial=[
                  {"fecha": "2026-11-17T10:00:00+00:00", "quien_hablo": "cliente",
                   "mensaje": "¿cuánto cuesta la limpieza?"},
                  {"fecha": "2026-11-17T10:01:00+00:00", "quien_hablo": "robot",
                   "mensaje": "La limpieza cuesta $600."},
              ]))

    print(f"{'ESCENARIO':<52} {'MOTIVO':<24} RESPUESTA")
    print("-" * 130)
    for nombre, mensaje, motivo, respuesta, botones in RESULTADOS:
        resp = respuesta.replace("\n", " ")[:95]
        print(f"{nombre:<52} {motivo:<24} {resp}{botones}")
    print("-" * 130)
    print(f"{len(RESULTADOS)} escenarios simulados contra el código real.")


if __name__ == "__main__":
    main()
