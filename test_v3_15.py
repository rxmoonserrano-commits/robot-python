"""Pruebas de la v3.15: urgencia inteligente (adelantar vs nueva).

Jose probó la urgencia en vivo con 2 citas registradas y pidió que
la inteligencia entienda si ADELANTA la cita que ya tiene o hace una
NUEVA. Mecánica (v3.15):
- Si el cliente tiene una cita propia futura y la primera hora
  libre es ANTES de esa cita → se propone ADELANTO (moverla), con
  botones "Adelantar cita" / "Dejarla como está" / "Hablar con
  persona".
- Si no tiene cita propia (las citas son de otros pacientes) → cita
  nueva urgente, como siempre.
- Si su cita ya está en la primera hora disponible → sin propuesta:
  el handoff sale igual y la IA lo explica.
La decisión la toma el código (`_plan_urgencia`) ANTES de llamar a
la IA; la IA solo lo dice con naturalidad.

Casos:
(a) Adelanto: cita propia + hueco antes → botones de adelanto,
    mensaje "Vi que ya tienes una cita el...", marco con el plan.
(b) Confirmar adelanto: crea la nueva, cancela la vieja, mueve el
    espejo (fecha/hora nuevas, URGENTE, notas), correo con el porqué,
    propuesta borrada.
(c) Dejarla igual: borra la propuesta, no toca calendario ni espejo.
(d) Citas de otros pacientes → cita nueva urgente (no adelanto).
(e) Cita ya en la primera hora → sin propuesta, handoff igual.
(f) extra_json del adelanto sobrevive (tipo, cita_id, fecha_vieja).
(g) "sí" por texto también adelanta (no crea una cita extra).
(h) Adelanto con profesional: la oferta dice con quién.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import (  # noqa: E402
    Dependencias,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _extra_propuesta_json,
    _parse_extra_propuesta,
    atender_boton,
    atender_mensaje,
)

TEL = "5216694608263"
AHORA_CERRADO = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"

FALLOS = []
TOTAL = [0]


def caso(nombre, ok, detalle=""):
    TOTAL[0] += 1
    if ok:
        print(f"  ok  {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"  FAIL {nombre} :: {detalle}")


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()


class DepsV315(Dependencias):
    """Falso con espejo configurable para probar el plan de urgencia."""

    def __init__(self, huecos=None, huecos_pro=None, espejo=None, agente_cola=None):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.mirror = []
        self.diagnosticos = []
        self.alertas_handoff = []
        self.alertas_urgentes = []
        self.alertas_confirmadas = []
        self.mensajes_al_agente = []
        self.huecos = huecos if huecos is not None else [LUNES, MARTES]
        self.huecos_pro = huecos_pro if huecos_pro is not None else []
        self.espejo = espejo if espejo is not None else []
        self.actualizaciones = []
        self.citas_canceladas = []

    # --- agente ---
    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_al_agente.append(mensaje)
        if self.agente_cola:
            return self.agente_cola.pop(0)
        if "[URGENTE]" in mensaje:
            return RespuestaAgente(respuesta_texto=(
                "Ay, qué mal rato, lo siento mucho. Te paso con una persona "
                "de inmediato para que te atiendan lo antes posible."))
        return RespuestaAgente(respuesta_texto="Claro, te ayudo.")

    # --- agenda ---
    def proximos_huecos_libres(self, conocimiento, ahora, cantidad=2, dias=3):
        return list(self.huecos)

    def proximos_huecos_profesionales(self, conocimiento, ahora, cantidad=2, dias=3):
        return list(self.huecos_pro)

    def duracion_servicio(self, motivo):
        return None

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        cita = {"nombre": nombre, "telefono": telefono, "motivo": motivo,
                "fecha_cita": fecha_cita, "nota": nota}
        self.citas.append(cita)
        return cita

    # --- espejo ---
    def registrar_cita_espejo(self, fila):
        self.mirror.append(fila)

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None,
                               recordatorio_enviado=None, urgencia=None,
                               nueva_fecha=None, nueva_hora_inicio=None,
                               nueva_hora_fin=None):
        self.actualizaciones.append({
            "telefono": telefono, "fecha_cita": fecha_cita, "estado": estado,
            "notas": notas, "recordatorio_enviado": recordatorio_enviado,
            "urgencia": urgencia, "nueva_fecha": nueva_fecha,
            "nueva_hora_inicio": nueva_hora_inicio,
            "nueva_hora_fin": nueva_hora_fin,
        })

    def leer_citas_espejo(self):
        return list(self.espejo)

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

    # --- avisos ---
    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_confirmadas.append({"nombre": nombre, "telefono": telefono,
                                         "motivo": motivo, "fecha_bonita": fecha_bonita})

    def alerta_cita_urgente(self, nombre, telefono, motivo, fecha_bonita, fecha, razon=""):
        self.alertas_urgentes.append({"nombre": nombre, "telefono": telefono,
                                      "motivo": motivo, "fecha_bonita": fecha_bonita,
                                      "razon": razon})

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha, resumen=""):
        self.alertas_handoff.append({"nombre": nombre, "telefono": telefono,
                                     "motivo": motivo, "resumen": resumen})

    def cancelar_cita(self, telefono, fecha_cita):
        self.citas_canceladas.append({"telefono": telefono, "fecha_cita": fecha_cita})
        return True

    def cancelar_cita_cliente(self, telefono):
        pass

    # --- WhatsApp / registro ---
    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, texto, botones))

    def enviar_foto(self, telefono, url):
        pass

    def registrar_conversacion(self, fecha, telefono, quien, texto, respondio, motivo):
        self.conversaciones.append({"quien": quien, "texto": texto, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"nombre": nombre, "telefono": telefono, "motivo": motivo,
                              "fecha_cita": fecha_cita, "estatus": estatus})

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        self.diagnosticos.append({"componente": componente, "estado": estado,
                                  "detalle": detalle})

    def leer_cliente(self, telefono):
        return None

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_conocimiento(self):
        return []

    def leer_fotos_oficiales(self):
        return []

    def leer_historial(self, telefono):
        return []

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []


def _urgencia(d, ahora=AHORA_CERRADO):
    limpiar()
    return atender_mensaje(d, TEL, "Jose Ramon", "me duele mucho la muela, es urgente",
                           con_ritmo=False, ahora=ahora)


def _espejo_propia():
    return [{
        "ID_Cita": "C-20261122185253-8263",
        "Teléfono": TEL,
        "Servicio": "Blanqueamiento dental",
        "Profesional": "Equipo de la clínica",
        "Fecha": "2026-11-24",
        "Hora_inicio": "09:00",
        "Hora_fin": "10:00",
        "Estado": "Confirmada",
        "Notas": "Paciente: Jose Ramon Serrano Sopeña",
        "Urgencia": "NO",
    }]


# ------------------------------------------------------------------
# (a) Adelanto: cita propia + hueco antes
# ------------------------------------------------------------------

def test_a_adelanto():
    d = DepsV315(espejo=_espejo_propia())
    r = _urgencia(d)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    botones = d.botones[0][2] if d.botones else []
    caso("(a) Adelanto: botones de adelanto",
         r.get("handoff") is True and len(d.botones) == 1
         and [b[0] for b in botones] == ["adelantar_cita", "dejar_cita_igual", "hablar_persona"],
         f"{r} {d.botones}")
    caso("(a) Adelanto: mensaje menciona la cita vieja y la nueva",
         d.botones and "Vi que ya tienes una cita el" in d.botones[0][1]
         and "Te la adelanto a" in d.botones[0][1], f"{d.botones}")
    caso("(a) Adelanto: propuesta guardada con tipo adelanto",
         propuesta.get("tipo") == "adelanto"
         and propuesta.get("cita_id") == "C-20261122185253-8263"
         and propuesta.get("fecha_cita") == LUNES
         and propuesta.get("servicio") == "Blanqueamiento dental", f"{propuesta}")
    caso("(a) Adelanto: el marco le avisa a la IA del plan",
         d.mensajes_al_agente and "adelantarla a" in d.mensajes_al_agente[0],
         f"{d.mensajes_al_agente}")
    limpiar()


# ------------------------------------------------------------------
# (b) Confirmar adelanto: mueve la cita
# ------------------------------------------------------------------

def test_b_confirmar_adelanto():
    d = DepsV315(espejo=_espejo_propia())
    _urgencia(d)
    r = atender_boton(d, TEL, "Jose Ramon", "adelantar_cita",
                      con_ritmo=False, ahora=AHORA_CERRADO)
    caso("(b) Confirmar adelanto: crea la cita en la hora nueva",
         len(d.citas) == 1 and d.citas[0]["fecha_cita"] == LUNES
         and "URGENTE" in d.citas[0]["nota"], f"{d.citas}")
    caso("(b) Confirmar adelanto: cancela la vieja",
         len(d.citas_canceladas) == 1
         and d.citas_canceladas[0]["fecha_cita"].startswith("2026-11-24T09:00"),
         f"{d.citas_canceladas}")
    caso("(b) Confirmar adelanto: espejo movido y marcado URGENTE",
         len(d.actualizaciones) == 1
         and d.actualizaciones[0]["estado"] == "Confirmada"
         and d.actualizaciones[0]["urgencia"] == "SI"
         and d.actualizaciones[0]["nueva_fecha"] == "2026-11-23"
         and d.actualizaciones[0]["nueva_hora_inicio"] == "09:00"
         and d.actualizaciones[0]["nueva_hora_fin"] == "10:00"
         and "Adelantada por urgencia" in str(d.actualizaciones[0]["notas"]),
         f"{d.actualizaciones}")
    caso("(b) Confirmar adelanto: correo urgente con el movimiento",
         len(d.alertas_urgentes) == 1
         and "Adelantada desde" in d.alertas_urgentes[0]["razon"],
         f"{d.alertas_urgentes}")
    caso("(b) Confirmar adelanto: propuesta borrada y respuesta enviada",
         TEL not in _CITAS_PENDIENTES
         and r.get("cita_adelantada") is True
         and any("Tu cita quedó para el" in t for _, t in d.textos), f"{r} {d.textos}")
    limpiar()


# ------------------------------------------------------------------
# (c) Dejarla igual
# ------------------------------------------------------------------

def test_c_dejar_igual():
    d = DepsV315(espejo=_espejo_propia())
    _urgencia(d)
    r = atender_boton(d, TEL, "Jose Ramon", "dejar_cita_igual",
                      con_ritmo=False, ahora=AHORA_CERRADO)
    caso("(c) Dejarla igual: sin tocar calendario ni espejo",
         TEL not in _CITAS_PENDIENTES and len(d.citas) == 0
         and len(d.citas_canceladas) == 0 and len(d.actualizaciones) == 0
         and r.get("cita_sin_cambio") is True, f"{r} {d.citas} {d.actualizaciones}")
    caso("(c) Dejarla igual: respuesta amable",
         any("queda como está" in t for _, t in d.textos), f"{d.textos}")
    limpiar()


# ------------------------------------------------------------------
# (d) Citas de otros pacientes → cita nueva
# ------------------------------------------------------------------

def test_d_citas_de_otros():
    espejo = [{
        "ID_Cita": "C-20261122185254-8263",
        "Teléfono": TEL,
        "Servicio": "Blanqueamiento dental",
        "Fecha": "2026-11-24",
        "Hora_inicio": "09:00",
        "Hora_fin": "10:00",
        "Estado": "Confirmada",
        "Notas": "Paciente: su hermana",
        "Urgencia": "NO",
    }]
    d = DepsV315(espejo=espejo)
    r = _urgencia(d)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    botones = d.botones[0][2] if d.botones else []
    caso("(d) Cita de otro paciente: cita nueva urgente, no adelanto",
         r.get("handoff") is True and len(d.botones) == 1
         and [b[0] for b in botones] == ["confirmar_cita", "cambiar_hora", "hablar_persona"]
         and propuesta.get("tipo", "") in ("", None)
         and "Te dejo lista tu cita" in d.botones[0][1], f"{r} {d.botones} {propuesta}")
    limpiar()


# ------------------------------------------------------------------
# (e) Cita ya en la primera hora → sin propuesta
# ------------------------------------------------------------------

def test_e_cita_en_primera_hora():
    espejo = [{
        "ID_Cita": "C-1",
        "Teléfono": TEL,
        "Servicio": "Blanqueamiento dental",
        "Fecha": "2026-11-23",
        "Hora_inicio": "09:00",
        "Hora_fin": "10:00",
        "Estado": "Confirmada",
        "Notas": "Paciente: Jose Ramon Serrano Sopeña",
        "Urgencia": "NO",
    }]
    d = DepsV315(espejo=espejo)
    r = _urgencia(d)
    caso("(e) Cita ya en la primera hora: sin botones, handoff igual",
         r.get("handoff") is True and len(d.botones) == 0
         and TEL not in _CITAS_PENDIENTES, f"{r} {d.botones}")
    caso("(e) Cita en primera hora: el marco lo explica",
         d.mensajes_al_agente and "primera hora" in d.mensajes_al_agente[0],
         f"{d.mensajes_al_agente}")
    limpiar()


# ------------------------------------------------------------------
# (f) extra_json del adelanto sobrevive
# ------------------------------------------------------------------

def test_f_extra_json():
    d = DepsV315(espejo=_espejo_propia())
    _urgencia(d)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    crudo = _extra_propuesta_json(propuesta)
    extra = _parse_extra_propuesta(crudo)
    caso("(f) Adelanto: extra_json conserva tipo, cita y fechas",
         extra.get("tipo") == "adelanto"
         and extra.get("cita_id") == "C-20261122185253-8263"
         and extra.get("fecha_vieja", "").startswith("2026-11-24T09:00")
         and extra.get("servicio") == "Blanqueamiento dental"
         and "urgencia" in extra.get("urgencia", "").lower(), f"{extra}")
    limpiar()


# ------------------------------------------------------------------
# (g) "sí" por texto también adelanta
# ------------------------------------------------------------------

def test_g_si_por_texto():
    d = DepsV315(espejo=_espejo_propia())
    _urgencia(d)
    atender_mensaje(d, TEL, "Jose Ramon", "sí",
                    con_ritmo=False, ahora=AHORA_CERRADO)
    caso("(g) 'sí' por texto: mueve la cita, no crea una extra",
         len(d.citas) == 1 and d.citas[0]["fecha_cita"] == LUNES
         and len(d.citas_canceladas) == 1
         and TEL not in _CITAS_PENDIENTES, f"{d.citas} {d.citas_canceladas}")
    limpiar()


# ------------------------------------------------------------------
# (h) Adelanto con profesional
# ------------------------------------------------------------------

def test_h_adelanto_con_profesional():
    d = DepsV315(espejo=_espejo_propia(),
                 huecos_pro=[{"inicio": LUNES, "profesional": "Dra. Ruiz"}])
    _urgencia(d)
    caso("(h) Adelanto con profesional: la oferta dice con quién",
         d.botones and "con la Dra. Ruiz" in d.botones[0][1], f"{d.botones}")
    limpiar()


def main():
    test_a_adelanto()
    test_b_confirmar_adelanto()
    test_c_dejar_igual()
    test_d_citas_de_otros()
    test_e_cita_en_primera_hora()
    test_f_extra_json()
    test_g_si_por_texto()
    test_h_adelanto_con_profesional()
    print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} casos ok")
    if FALLOS:
        print("FALLARON:", FALLOS)
        sys.exit(1)


if __name__ == "__main__":
    main()
