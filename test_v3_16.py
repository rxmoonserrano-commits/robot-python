"""Pruebas de la v3.16: parche robusto (comunicación + fricciones).

Jose pidió aplicar todas las correcciones del análisis del motor
conversacional y adelantar bugs, paredes y fricciones de las
personas. Esta versión:

- _es_afirmacion con lista blanca: "me duele es urgente" ya no es
  un "sí" (el bug que Jose encontró en vivo).
- _es_urgencia e _intencion_cambio con negaciones: "no me duele
  nada" no es urgencia; "no quiero cancelar" no cancela.
- La cita urgente nueva se confirma aunque haya 2 citas (el tope
  ya no la bloquea al confirmar).
- El tope de citas ofrece MOVER la cita propia con botones en vez
  del muro; sin cita propia, el muro de siempre.
- Contexto de tiempo completo: días desde el último mensaje en
  cualquier etapa + cuánto falta para la cita vigente.
- Acción y confianza para la IA: terminar / no_responder /
  pedir_info / confianza baja dos veces → persona.

Casos:
(a) _es_afirmacion: 29 casos de lista blanca.
(b) _es_urgencia con negaciones.
(c) _intencion_cambio con negaciones.
(d) El caso de Jose: propuesta pendiente + "me duele es urgente"
    → flujo de urgencia, NO el muro del tope.
(e) Urgencia nueva con 2 citas ajenas: se confirma pese al tope.
(f) Tope con cita propia: ofrece mover (botones); confirmar mueve;
    dejarla igual no toca nada.
(g) Tope sin cita propia: mensaje del tope de siempre.
(h) Tiempo: días desde el último mensaje en etapa pregunto;
    cuánto falta para la cita en el contexto.
(i) Acción/confianza: no_responder calla; terminar marca cerrada;
    baja dos veces → handoff; accion agendar dispara la propuesta.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente, _normalizar, guion  # noqa: E402
from robot.logic import (  # noqa: E402
    Dependencias,
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_afirmacion,
    _es_urgencia,
    _intencion_cambio,
    atender_boton,
    atender_mensaje,
)

TEL = "5216694608263"
AHORA = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)  # domingo
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"

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
    _BAJA_CONFIANZA.clear()


class DepsV316(Dependencias):
    """Falso configurable: espejo, historial, cliente, agente encolado."""

    def __init__(self, huecos=None, espejo=None, agente_cola=None,
                 historial=None, cliente=None):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []
        self.conversaciones = []
        self.citas = []
        self.citas_canceladas = []
        self.actualizaciones_espejo = []
        self.alertas_handoff = []
        self.alertas_urgentes = []
        self.alertas_confirmadas = []
        self.mensajes_al_agente = []
        self.memorias = []
        self.huecos = huecos if huecos is not None else [LUNES, MARTES]
        self.espejo = espejo if espejo is not None else []
        self.historial = historial if historial is not None else []
        self.cliente = cliente

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

    def hora_libre(self, fecha_iso):
        return True

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        cita = {"nombre": nombre, "telefono": telefono, "motivo": motivo,
                "fecha_cita": fecha_cita, "nota": nota}
        self.citas.append(cita)
        return cita

    def cancelar_cita(self, telefono, fecha_cita):
        self.citas_canceladas.append(fecha_cita)
        return True

    def leer_citas_espejo(self):
        return list(self.espejo)

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None,
                               recordatorio_enviado=None, urgencia=None,
                               nueva_fecha=None, nueva_hora_inicio=None,
                               nueva_hora_fin=None):
        self.actualizaciones_espejo.append({
            "telefono": telefono, "fecha_cita": fecha_cita, "estado": estado,
            "notas": notas, "urgencia": urgencia, "nueva_fecha": nueva_fecha,
            "nueva_hora_inicio": nueva_hora_inicio,
            "nueva_hora_fin": nueva_hora_fin})

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_confirmadas.append(motivo)

    def alerta_cita_urgente(self, nombre, telefono, motivo, fecha_bonita, fecha, razon=""):
        self.alertas_urgentes.append(razon)

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha, resumen=""):
        self.alertas_handoff.append(motivo)

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

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        self.memorias.append({
            "resumen": resumen, "interes": interes,
            "proxima_accion": proxima_accion, "preferencias": preferencias})

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []


def espejo_dos():
    """Su cita del martes + la de su hermana del miércoles."""
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


def espejo_ajenas():
    """Dos citas, ambas de otra paciente (sin cita propia)."""
    return [
        {"ID_Cita": "C-1", "Teléfono": TEL, "Servicio": "Blanqueamiento dental",
         "Fecha": "2026-11-24", "Hora_inicio": "09:00", "Hora_fin": "10:00",
         "Estado": "Confirmada", "Notas": "Paciente: su hermana",
         "Urgencia": "NO"},
        {"ID_Cita": "C-2", "Teléfono": TEL, "Servicio": "Blanqueamiento dental",
         "Fecha": "2026-11-25", "Hora_inicio": "09:00", "Hora_fin": "10:00",
         "Estado": "Confirmada", "Notas": "Paciente: su hermana",
         "Urgencia": "NO"},
    ]


def propuesta_nueva():
    """Propuesta pendiente tipo nueva (como la de las 11:36pm)."""
    return {
        "nombre": "Jose Ramon", "motivo": "me duele es urgente",
        "fecha_cita": LUNES, "fecha_bonita": "lunes 23 de noviembre a las 09:00",
        "creado_en": "2026-11-22T09:00:00+00:00",
        "profesional": "", "nombre_paciente": "", "relacion_paciente": "",
        "numero_paciente": "", "cita2": None,
        "urgencia": "Urgencia del cliente: me duele es urgente",
    }


# ---- (a) _es_afirmacion: lista blanca ----
limpiar()
_afirm = {
    "me duele es urgente": False, "me urge una cita": False,
    "me puedes ayudar": False, "si me duele": False,
    "claro que me duele": False, "me va": True, "si": True, "sí": True,
    "claro": True, "ok": True, "me parece bien": True, "de acuerdo": True,
    "estoy de acuerdo": True, "dale": True, "va": True, "sale": True,
    "si me va esa fecha": True, "me queda bien": True, "claro que si": True,
    "ok perfecto": True, "si gracias": False, "mejor el sábado": False,
    "no": False, "nop": False, "": False, "👍": True, "???": False,
    "confirmo": True, "si esta bien": True,
}
_mal = [(t, _es_afirmacion(t), e) for t, e in _afirm.items() if _es_afirmacion(t) != e]
caso("(a) _es_afirmacion lista blanca (29 casos)", not _mal, f"{_mal}")

# ---- (b) _es_urgencia con negaciones ----
_u = {
    "me duele mucho la muela": True, "es urgente": True,
    "no me duele nada": False, "no es urgente, solo quiero agendar": False,
    "no, me duele mucho": True, "no es urgente pero me duele": True,
    "no puedo esperar": True, "¿duele la limpieza?": False,
    "quiero agendar sin dolor": False, "sangrando mucho": True,
    "no me duele": False,
}
_mal = [(t, _es_urgencia(t), e) for t, e in _u.items() if _es_urgencia(t) != e]
caso("(b) _es_urgencia con negaciones", not _mal, f"{_mal}")

# ---- (c) _intencion_cambio con negaciones ----
_ic = {
    "no quiero cancelar": None, "quiero cancelar": "cancelar",
    "no quiero cambiar": None, "quiero cambiar mi cita": "cambiar",
    "cancelar por favor": "cancelar", "no lo canceles": None,
    "dejalo asi": None, "mejor no": "cambiar",
}
_mal = [(t, _intencion_cambio(t), e) for t, e in _ic.items() if _intencion_cambio(t) != e]
caso("(c) _intencion_cambio con negaciones", not _mal, f"{_mal}")

# ---- (d) El caso de Jose: propuesta pendiente + urgencia ----
limpiar()
d = DepsV316(espejo=espejo_dos())
_CITAS_PENDIENTES[TEL] = propuesta_nueva()
r = atender_mensaje(d, TEL, "Jose Ramon", "me duele es urgente",
                    con_ritmo=False, ahora=AHORA)
caso("(d) Propuesta + urgencia: NO es el muro del tope",
     r.get("motivo") != "tope de citas" and not any("Ya tienes 2 citas" in t for t in d.textos),
     f"motivo={r.get('motivo')} textos={d.textos}")
caso("(d) Propuesta + urgencia: corre el flujo de urgencia (handoff)",
     r.get("motivo") == "handoff" and len(d.alertas_handoff) == 1,
     f"motivo={r.get('motivo')} alertas={d.alertas_handoff}")
caso("(d) La propuesta sigue pendiente (no se confirma por error)",
     TEL in _CITAS_PENDIENTES and len(d.citas) == 0,
     f"pendiente={TEL in _CITAS_PENDIENTES} citas={d.citas}")
limpiar()

# ---- (e) Urgencia nueva se confirma pese al tope ----
limpiar()
d = DepsV316(espejo=espejo_ajenas())
r = atender_mensaje(d, TEL, "Jose Ramon", "me duele es urgente",
                    con_ritmo=False, ahora=AHORA)
caso("(e) Urgencia sin cita propia: propuesta nueva con botones",
     (_CITAS_PENDIENTES.get(TEL) or {}).get("tipo") is None
     and TEL in _CITAS_PENDIENTES and len(d.botones) == 1,
     f"pendiente={_CITAS_PENDIENTES.get(TEL)} botones={d.botones}")
r2 = atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                   con_ritmo=False, ahora=AHORA)
caso("(e) Confirmar la urgente con 2 citas: SÍ se crea (sin muro)",
     len(d.citas) == 1 and r2.get("motivo") != "tope de citas",
     f"citas={d.citas} motivo={r2.get('motivo')}")
caso("(e) Correo de urgencia enviado",
     len(d.alertas_urgentes) == 1, f"{d.alertas_urgentes}")
limpiar()

# ---- (f) Tope con cita propia: ofrece mover ----
limpiar()
d = DepsV316(espejo=espejo_dos(), agente_cola=[RespuestaAgente(
    respuesta_texto="Te propongo tu cita.",
    quiere_agendar="si", fecha_cita=LUNES, motivo="Blanqueamiento dental")])
r = atender_mensaje(d, TEL, "Jose Ramon", "quiero agendar mañana",
                    con_ritmo=False, ahora=AHORA)
caso("(f) Tope con cita propia: ofrece mover (no muro)",
     (_CITAS_PENDIENTES.get(TEL) or {}).get("tipo") == "mover"
     and any("Te la muevo" in x[0] for x in d.botones)
     and not any("Ya tienes 2 citas" in t for t in d.textos),
     f"pendiente={_CITAS_PENDIENTES.get(TEL)} botones={d.botones} textos={d.textos}")
r2 = atender_boton(d, TEL, "Jose Ramon", "adelantar_cita",
                   con_ritmo=False, ahora=AHORA)
caso("(f) Confirmar mover: crea la nueva y cancela la vieja",
     len(d.citas) == 1 and len(d.citas_canceladas) == 1
     and d.citas_canceladas[0].startswith("2026-11-24"),
     f"citas={d.citas} canceladas={d.citas_canceladas}")
caso("(f) Mover marca Urgencia=NO en el espejo",
     any(u["urgencia"] == "NO" for u in d.actualizaciones_espejo),
     f"{d.actualizaciones_espejo}")
caso("(f) Mover manda correo normal (no urgente)",
     len(d.alertas_confirmadas) == 1 and len(d.alertas_urgentes) == 0,
     f"confirmadas={d.alertas_confirmadas} urgentes={d.alertas_urgentes}")
limpiar()

limpiar()
d = DepsV316(espejo=espejo_dos(), agente_cola=[RespuestaAgente(
    respuesta_texto="Te propongo tu cita.",
    quiere_agendar="si", fecha_cita=LUNES, motivo="Blanqueamiento dental")])
atender_mensaje(d, TEL, "Jose Ramon", "quiero agendar mañana",
                con_ritmo=False, ahora=AHORA)
r3 = atender_boton(d, TEL, "Jose Ramon", "dejar_cita_igual",
                   con_ritmo=False, ahora=AHORA)
caso("(f) Dejarla igual: borra propuesta, no toca calendario",
     TEL not in _CITAS_PENDIENTES and len(d.citas) == 0
     and len(d.citas_canceladas) == 0
     and "Te paso con una persona" not in " ".join(d.textos),
     f"textos={d.textos}")
limpiar()

# ---- (g) Tope sin cita propia: muro de siempre ----
limpiar()
d = DepsV316(espejo=espejo_ajenas(), agente_cola=[RespuestaAgente(
    respuesta_texto="Te propongo tu cita.",
    quiere_agendar="si", fecha_cita=LUNES, motivo="Blanqueamiento dental")])
r = atender_mensaje(d, TEL, "Jose Ramon", "quiero agendar mañana",
                    con_ritmo=False, ahora=AHORA)
caso("(g) Tope sin cita propia: mensaje del tope, sin propuesta",
     any("Ya tienes 2 citas" in t for t in d.textos) and TEL not in _CITAS_PENDIENTES,
     f"textos={d.textos} pendiente={TEL in _CITAS_PENDIENTES}")
limpiar()

# ---- (h) Tiempo: días desde el último mensaje (etapa pregunto) ----
limpiar()
d = DepsV316(
    historial=[
        {"fecha": "2026-11-17T10:00:00+00:00", "quien_hablo": "cliente",
         "mensaje": "¿cuánto cuesta la limpieza?"},
        {"fecha": "2026-11-17T10:01:00+00:00", "quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600."},
    ],
    agente_cola=[RespuestaAgente(respuesta_texto="La limpieza cuesta $600.")])
atender_mensaje(d, TEL, "Jose Ramon", "¿y el blanqueamiento?",
                con_ritmo=False, ahora=AHORA)
caso("(h) Pregunta tras 5 días: el contexto dice cuánto pasó",
     any("desde su último mensaje" in m for m in d.mensajes_al_agente),
     f"{d.mensajes_al_agente}")
limpiar()

limpiar()
d = DepsV316(
    cliente={"estatus": "agendado", "fecha_cita": MARTES,
             "motivo": "Blanqueamiento dental", "nombre": "Jose Ramon"},
    agente_cola=[RespuestaAgente(respuesta_texto="Claro, te ayudo.")])
atender_mensaje(d, TEL, "Jose Ramon", "hola",
                con_ritmo=False, ahora=AHORA)
caso("(h) Con cita vigente: el contexto dice cuánto falta",
     any("Su cita es" in m for m in d.mensajes_al_agente),
     f"{d.mensajes_al_agente}")
limpiar()

# ---- (i) Acción y confianza ----
limpiar()
d = DepsV316(agente_cola=[RespuestaAgente(
    respuesta_texto="", accion="no_responder")])
r = atender_mensaje(d, TEL, "Jose Ramon", "compra mi curso de trading",
                    con_ritmo=False, ahora=AHORA)
caso("(i) no_responder: silencio total",
     r.get("respondio") is False and len(d.textos) == 0 and len(d.botones) == 0,
     f"r={r} textos={d.textos}")
limpiar()

limpiar()
d = DepsV316(agente_cola=[RespuestaAgente(
    respuesta_texto="Quedamos a tus órdenes.",
    accion="terminar", resumen_cliente="Preguntó precios.")])
r = atender_mensaje(d, TEL, "Jose Ramon", "gracias, ya no",
                    con_ritmo=False, ahora=AHORA)
caso("(i) terminar: cierra cálido y marca la memoria cerrada",
     len(d.textos) == 1 and any(m["proxima_accion"] == "cerrada" for m in d.memorias),
     f"textos={d.textos} memorias={d.memorias}")
limpiar()

limpiar()
d = DepsV316(agente_cola=[
    RespuestaAgente(respuesta_texto="¿Me dices qué necesitas?",
                    confianza="baja"),
    RespuestaAgente(respuesta_texto="¿Te refieres a la cita?",
                    confianza="baja"),
])
r1 = atender_mensaje(d, TEL, "Jose Ramon", "asdf qwer",
                     con_ritmo=False, ahora=AHORA)
r2 = atender_mensaje(d, TEL, "Jose Ramon", "zxcv",
                     con_ritmo=False, ahora=AHORA)
caso("(i) Confianza baja la primera vez: pregunta de aclaración",
     r1.get("motivo") != "handoff" and d.textos[0] == "¿Me dices qué necesitas?",
     f"r1={r1} textos={d.textos}")
caso("(i) Confianza baja la segunda vez: pasa a una persona",
     r2.get("motivo") == "handoff" and len(d.alertas_handoff) == 1,
     f"r2={r2} alertas={d.alertas_handoff}")
limpiar()

limpiar()
_r = _normalizar({"respuesta_texto": "Te propongo tu cita.",
                  "accion": "agendar", "fecha_cita": LUNES})
caso("(i) _normalizar: accion agendar dispara quiere_agendar",
     _r.quiere_agendar == "si" and _r.accion == "agendar", f"{_r}")
_r2 = _normalizar({"respuesta_texto": "Te paso con alguien.",
                   "accion": "pasar_persona"})
caso("(i) _normalizar: accion pasar_persona dispara handoff",
     _r2.necesita_handoff == "si", f"{_r2}")
_r3 = _normalizar({"respuesta_texto": "Hola.", "accion": "inventada",
                   "confianza": "altisima"})
caso("(i) _normalizar: valores desconocidos quedan vacíos",
     _r3.accion == "" and _r3.confianza == "", f"{_r3}")
caso("(i) El guion trae accion/confianza/info_faltante",
     all(p in guion() for p in ("accion", "confianza", "info_faltante")),
     "")
limpiar()

print()
if FALLOS:
    print(f"FALLOS ({len(FALLOS)}): {FALLOS}")
    sys.exit(1)
print(f"{TOTAL[0]}/{TOTAL[0]} casos ok (test_v3_16)")
