"""Pruebas de la versión 3.3 (calidad para el dueño y para su cliente), SIN internet.

Lo nuevo de la v3.3:
(a) Horas libres de verdad: el agente solo ofrece huecos que existen
    en el calendario (una sola llamada freebusy). Si no hay huecos, el
    contexto dice que la agenda está llena y el robot no inventa horas.
(b) Preguntar el nombre: el guion lo pide una sola vez, cuando encaje
    con naturalidad (al saludar o al agendar). El contexto ya no lo
    fuerza antes de responder (v3.4.2: sonaba a robot).
(c) Urgencias a humano: "me duele", "urgente", "sangrando"... van
    directo a una persona, sin llamar a la IA. "¿duele la limpieza?"
    NO es urgencia: es una pregunta.
(d) Resumen de la mañana: cada día 08:00, por correo: qué pasó en las
    últimas 24 h, quién necesita una persona, propuestas sin contestar
    y las citas de hoy.
(e) Alertas de lead caliente y de cita confirmada: el dueño se entera
    en el momento, no el lunes.
(f) Anti-abuso: más de 10 mensajes en 60 s por teléfono → se le avisa
    una vez y se ignoran los demás hasta que pase la ventana.

Uso:  python test_v3_3.py
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import robot.agent as agent_mod
import robot.booking as booking_mod
import robot.logic as logic_mod
import robot.report as report_mod
from robot.abuso import Limitador
from robot.agent import RespuestaAgente, guion
from robot.logic import atender_boton, atender_mensaje, horarios_por_dia

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]
TELEFONO = "5216694608263"
# Viernes 13 de noviembre de 2026, 09:00 hora de Mazatlán.
VIERNES = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
HORARIOS = horarios_por_dia(CONOCIMIENTO)


def fila(quien, mensaje, motivo=""):
    return {"fecha": "2026-11-13T04:00:00+00:00", "telefono": TELEFONO,
            "quien_hablo": quien, "mensaje": mensaje, "robot_respondio": "si",
            "motivo": motivo}


class DepsV33:
    """Servicios de mentira, con huecos libres y alertas de la v3.3."""

    def __init__(self, historial=None, respuesta_agente=None, cliente=None,
                 huecos=None, huecos_falla=False):
        self.historial = historial or []
        self.respuesta_agente = respuesta_agente
        self.cliente = cliente
        self.huecos = huecos
        self.huecos_falla = huecos_falla
        self.memoria = {}
        self.propuestas_guardadas = {}
        self.conversaciones = []
        self.textos_enviados = []
        self.botones_enviados = []
        self.diagnostico = []
        self.mensajes_al_agente = []
        self.alertas_handoff = []
        self.alertas_cita = []
        self.alertas_caliente = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        base = dict(self.cliente or {})
        base.update(self.memoria.get(telefono, {}))
        return base or None

    def cancelar_cita(self, telefono, fecha_cita):
        return False

    def cancelar_cita_cliente(self, telefono):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        self.propuestas_guardadas[telefono] = dict(propuesta)

    def borrar_propuesta(self, telefono):
        self.propuestas_guardadas.pop(telefono, None)

    def leer_propuestas(self):
        return []

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def proximos_huecos_libres(self, conocimiento, ahora):
        if self.huecos_falla:
            raise RuntimeError("Calendar no contestó")
        return list(self.huecos) if self.huecos is not None else []

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return FOTOS

    def leer_historial(self, telefono):
        return list(self.historial) + [c for c in self.conversaciones
                                        if c["telefono"] == telefono]

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
                                    "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp",
                          estatus="en conversacion", handoff="no"):
        pass

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_al_agente.append(mensaje)
        return self.respuesta_agente

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        return {"inicio": fecha_cita}

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas_handoff.append((nombre, telefono, motivo))

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_cita.append((nombre, telefono, motivo, fecha_bonita))

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas_caliente.append((nombre, telefono, motivo))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def enviar_botones(self, telefono, texto, botones):
        self.botones_enviados.append((telefono, texto, botones))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        self.diagnostico.append({"componente": componente, "estado": estado,
                                 "detalle": detalle, "telefono": telefono,
                                 "contexto": contexto})


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


class _FreebusyFalso:
    """Cadena freebusy().query().execute() con la lista de ocupados que se le dé."""

    def __init__(self, busy, llamadas):
        self._busy = busy
        self._llamadas = llamadas

    def freebusy(self):
        return self

    def query(self, body=None):
        self._llamadas.append(body)
        return self

    def execute(self):
        return {"calendars": {"primary": {"busy": self._busy}}}


def main():
    # ---- (a) Huecos libres: una sola llamada a Calendar ----
    busy = [{"start": "2026-11-13T10:00:00-07:00", "end": "2026-11-13T11:00:00-07:00"}]
    llamadas = []
    booking_mod._HUECOS_CACHE.clear()
    with patch.object(booking_mod, "_servicio_calendar",
                      lambda: _FreebusyFalso(busy, llamadas)):
        huecos = booking_mod.proximos_huecos_libres(HORARIOS, VIERNES, usar_cache=False)
    caso("(a) Huecos: salta la hora ocupada y da los 2 siguientes libres",
         huecos == ["2026-11-13T11:00:00-07:00", "2026-11-13T12:00:00-07:00"],
         f"salió: {huecos}")
    caso("(a) Huecos: una sola llamada a Calendar para todo el rango",
         len(llamadas) == 1 and llamadas[0]["timeMin"].startswith("2026-11-13"),
         f"llamadas: {len(llamadas)}")

    tarde = datetime(2026, 11, 13, 17, 30, tzinfo=timezone.utc)  # 10:30 Mazatlán
    booking_mod._HUECOS_CACHE.clear()
    with patch.object(booking_mod, "_servicio_calendar",
                      lambda: _FreebusyFalso([], llamadas)):
        huecos = booking_mod.proximos_huecos_libres(HORARIOS, tarde, usar_cache=False)
    caso("(a) Huecos: no ofrece horas que ya pasaron (10:00 no, 11:00 sí)",
         huecos == ["2026-11-13T11:00:00-07:00", "2026-11-13T12:00:00-07:00"],
         f"salió: {huecos}")

    # Viernes y sábado llenos (dias=1: viernes y sábado): no hay huecos.
    lleno = [
        {"start": "2026-11-13T09:00:00-07:00", "end": "2026-11-13T18:00:00-07:00"},
        {"start": "2026-11-14T09:00:00-07:00", "end": "2026-11-14T14:00:00-07:00"},
    ]
    booking_mod._HUECOS_CACHE.clear()
    with patch.object(booking_mod, "_servicio_calendar",
                      lambda: _FreebusyFalso(lleno, llamadas)):
        huecos = booking_mod.proximos_huecos_libres(HORARIOS, VIERNES, dias=1, usar_cache=False)
    caso("(a) Huecos: agenda llena → lista vacía (el robot no inventa)",
         huecos == [], f"salió: {huecos}")

    # Caché: la segunda llamada con los mismos parámetros no toca Calendar.
    booking_mod._HUECOS_CACHE.clear()
    llamadas.clear()
    with patch.object(booking_mod, "_servicio_calendar",
                      lambda: _FreebusyFalso([], llamadas)):
        booking_mod.proximos_huecos_libres(HORARIOS, VIERNES)
        booking_mod.proximos_huecos_libres(HORARIOS, VIERNES)
    caso("(a) Huecos: la segunda llamada usa la caché (60 s)",
         len(llamadas) == 1, f"llamadas: {len(llamadas)}")
    booking_mod._HUECOS_CACHE.clear()

    # Si Calendar falla, []: quien llama decide (nunca se inventa una hora).
    booking_mod._HUECOS_CACHE.clear()
    with patch.object(booking_mod, "_servicio_calendar", side_effect=RuntimeError("sin red")):
        huecos = booking_mod.proximos_huecos_libres(HORARIOS, VIERNES, usar_cache=False)
    caso("(a) Huecos: si Calendar falla, [] (no se inventa nada)",
         huecos == [], f"salió: {huecos}")

    # ---- (a) El contexto lleva los huecos libres ----
    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"),
        huecos=["2026-11-14T10:00:00-07:00", "2026-11-16T09:00:00-07:00"])
    atender_mensaje(d, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(a) Contexto: trae los huecos libres con fecha bonita",
         "sábado 14 de noviembre a las 10:00" in mensaje
         and "lunes 16 de noviembre a las 09:00" in mensaje
         and "SOLO estos" in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")
    caso("(a) Contexto: el agente recibe el mensaje (se llamó a Gemini)",
         len(d.mensajes_al_agente) == 1, f"llamadas: {len(d.mensajes_al_agente)}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"),
        huecos=[])
    atender_mensaje(d, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(a) Contexto: sin huecos, dice que la agenda está llena",
         "agenda está llena" in mensaje and "SOLO estos" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"),
        huecos_falla=True)
    atender_mensaje(d, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(a) Contexto: si Calendar falla, no dice ni huecos ni 'llena'",
         "huecos libres" not in mensaje and "agenda está llena" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="Hola, Jose Ramon. ¿Qué necesitas?",
            quiere_agendar="no", nombre="Jose Ramon"),
        huecos=["2026-11-14T10:00:00-07:00"])
    atender_mensaje(d, TELEFONO, "Jose Ramon", "hola",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(a) Contexto: un saludo no calcula huecos (no se ofrecen)",
         "huecos libres" not in mensaje and "agenda está llena" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    # ---- (b) Preguntar el nombre, una sola vez ----
    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", motivo="Limpieza"))
    atender_mensaje(d, TELEFONO, "", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(b) Nombre: el contexto ya no lo fuerza (lo pide el guion)",
         "Me das tu nombre completo" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"))
    atender_mensaje(d, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(b) Nombre: si ya lo sabe, no lo vuelve a preguntar",
         "Me das tu nombre completo" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    d = DepsV33(
        historial=[fila("robot", "Hola, ¿con quién tengo el gusto?")],
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="no", motivo="Limpieza"))
    atender_mensaje(d, TELEFONO, "", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    mensaje = d.mensajes_al_agente[0] if d.mensajes_al_agente else ""
    caso("(b) Nombre: si ya lo preguntó en el último mensaje, no repite",
         "Me das tu nombre completo" not in mensaje,
         f"mensaje al agente: {mensaje[:300]!r}")

    # ---- (c) Urgencias a humano, sin llamar a la IA ----
    for texto_urgente in ("me duele mucho la muela",
                          "es una urgencia, me estoy sangrando",
                          "me duele horrible, es urgente"):
        d = DepsV33(
            respuesta_agente=RespuestaAgente(
                respuesta_texto="La limpieza cuesta $600.",
                quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"))
        r = atender_mensaje(d, TELEFONO, "Jose Ramon", texto_urgente,
                            con_ritmo=False, ahora=VIERNES)
        caso(f"(c) Urgencia: {texto_urgente!r} → handoff, sin llamar al agente",
             r.get("handoff") is True
             and len(d.mensajes_al_agente) == 0
             and len(d.alertas_handoff) == 1
             and "persona" in (d.textos_enviados[0][1] if d.textos_enviados else ""),
             f"resultado={r} agente={len(d.mensajes_al_agente)} alertas={d.alertas_handoff}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza no suele doler.",
            quiere_agendar="no", nombre="Jose Ramon", motivo="Limpieza"))
    r = atender_mensaje(d, TELEFONO, "Jose Ramon", "¿duele la limpieza?",
                        con_ritmo=False, ahora=VIERNES)
    caso("(c) Urgencia: '¿duele la limpieza?' es una pregunta, va al agente",
         r.get("handoff") is not True and len(d.mensajes_al_agente) == 1
         and len(d.alertas_handoff) == 0,
         f"resultado={r} agente={len(d.mensajes_al_agente)}")

    # ---- (g) v3.3.1: en un handoff NORMAL el cliente también recibe el texto ----
    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="Claro, te paso con una persona del negocio.",
            quiere_agendar="no", necesita_handoff="si",
            motivo_handoff="El cliente pidió hablar con el encargado",
            nombre="Jose Ramon", motivo="Quiere hablar con el encargado"))
    r = atender_mensaje(d, TELEFONO, "Jose Ramon",
                        "son unos rateros, quiero hablar con el encargado",
                        con_ritmo=False, ahora=VIERNES)
    caso("(g) Handoff normal: el cliente recibe el texto (antes quedaba en silencio)",
         r.get("handoff") is True
         and len(d.textos_enviados) == 1
         and "persona" in d.textos_enviados[0][1]
         and len(d.alertas_handoff) == 1,
         f"resultado={r} enviados={d.textos_enviados} alertas={d.alertas_handoff}")
    fila_robot = [c for c in d.conversaciones
                  if c["quien_hablo"] == "robot" and c["motivo"] == "handoff"]
    caso("(g) Handoff normal: queda registrado y respondio es True",
         r.get("respondio") is True and len(fila_robot) == 1
         and fila_robot[0]["mensaje"].startswith("Claro, te paso"),
         f"resultado={r} filas={fila_robot}")

    # ---- (e) Alertas de cita confirmada y de lead caliente ----
    logic_mod._CITAS_PENDIENTES.clear()
    logic_mod._CITAS_PENDIENTES[TELEFONO] = {
        "nombre": "Jose Ramon", "motivo": "Limpieza dental",
        "fecha_cita": "2026-11-14T10:00:00-07:00",
        "fecha_bonita": "sábado 14 de noviembre a las 10:00",
        "creado_en": "2026-11-13T16:00:00+00:00",
    }
    d = DepsV33()
    r = atender_boton(d, TELEFONO, "Jose Ramon", "confirmar_cita", con_ritmo=False)
    logic_mod._CITAS_PENDIENTES.clear()
    caso("(e) Cita confirmada: el botón Confirmar avisa al dueño por correo",
         r.get("respondio") is True and len(d.alertas_cita) == 1
         and d.alertas_cita[0][0] == "Jose Ramon"
         and d.alertas_cita[0][3] == "sábado 14 de noviembre a las 10:00",
         f"resultado={r} alertas={d.alertas_cita}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="Claro, te la agendo para el sábado.",
            quiere_agendar="si", fecha_cita="2026-11-14T10:00:00-07:00",
            nombre="Jose Ramon", motivo="Limpieza dental"))
    atender_mensaje(d, TELEFONO, "Jose Ramon", "quiero una cita para la limpieza",
                    con_ritmo=False, ahora=VIERNES)
    caso("(e) Lead caliente: 'quiero una cita' → correo al dueño en el momento",
         len(d.alertas_caliente) == 1 and d.alertas_caliente[0][0] == "Jose Ramon",
         f"alertas={d.alertas_caliente}")

    d = DepsV33(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600.",
            quiere_agendar="si", fecha_cita="2026-11-14T10:00:00-07:00",
            nombre="Jose Ramon", motivo="Limpieza dental"))
    atender_mensaje(d, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=VIERNES)
    caso("(e) Lead caliente: solo preguntar el precio NO avisa (no es caliente)",
         len(d.alertas_caliente) == 0,
         f"alertas={d.alertas_caliente}")

    # ---- (d) Resumen de la mañana ----
    ahora_real = datetime.now(timezone.utc)
    ayer = (ahora_real - timedelta(hours=12)).isoformat()
    hace_8_dias = (ahora_real - timedelta(days=8)).isoformat()
    conversaciones = [
        {"fecha": ayer, "telefono": TELEFONO, "quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600.", "robot_respondio": "si", "motivo": "Limpieza"},
        {"fecha": ayer, "telefono": "5216694608264", "quien_hablo": "robot",
         "mensaje": "Hola.", "robot_respondio": "si", "motivo": "Saludo"},
        {"fecha": hace_8_dias, "telefono": TELEFONO, "quien_hablo": "robot",
         "mensaje": "Viejo.", "robot_respondio": "si", "motivo": "Limpieza"},
    ]
    clientes = [
        {"fecha": ayer, "nombre": "Jose Ramon", "telefono": TELEFONO,
         "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
         "estatus": "en conversacion", "handoff": "no"},
        {"fecha": ayer, "nombre": "Maria", "telefono": "5216694608264",
         "motivo": "Me duele la muela", "fecha_cita": "", "origen": "whatsapp",
         "estatus": "en conversacion", "handoff": "si"},
        {"fecha": ayer, "nombre": "Pedro", "telefono": "5216694608265",
         "motivo": "Limpieza", "fecha_cita": ahora_real.isoformat(),
         "origen": "whatsapp", "estatus": "agendado", "handoff": "no"},
    ]
    propuestas = [
        {"telefono": TELEFONO, "nombre": "Jose Ramon", "motivo": "Limpieza dental",
         "fecha_cita": "2026-11-14T10:00:00-07:00",
         "fecha_bonita": "sábado 14 de noviembre a las 10:00",
         "creado_en": ayer, "apartado": "si", "aparta_hasta": "mañana sábado 14"},
    ]
    enviados = []

    def _correo_falso(destinatario, asunto, cuerpo):
        enviados.append((destinatario, asunto, cuerpo))

    with patch.object(report_mod, "leer_pestana",
                      side_effect=lambda tab: conversaciones if tab == "Conversaciones" else clientes), \
         patch.object(report_mod, "leer_propuestas", lambda: propuestas), \
         patch.object(report_mod, "enviar_correo", _correo_falso):
        resultado = report_mod.generar_resumen_manana()
    caso("(d) Resumen: cuenta solo las últimas 24 h (no lo de hace 8 días)",
         resultado["mensajes_atendidos"] == 2
         and resultado["clientes_calificados"] == 3
         and resultado["handoffs"] == 1
         and resultado["citas_agendadas"] == 1,
         f"resultado={resultado}")
    cuerpo = enviados[0][2] if enviados else ""
    caso("(d) Resumen: trae pendientes, propuestas y la cita de hoy",
         "Maria" in cuerpo and "Me duele la muela" in cuerpo
         and "Jose Ramon" in cuerpo and "apartado hasta mañana sábado 14" in cuerpo
         and "Pedro" in cuerpo,
         f"cuerpo: {cuerpo[:400]!r}")
    caso("(d) Resumen: el asunto es el de la mañana, no el semanal",
         enviados and enviados[0][1].startswith("Resumen de la mañana"),
         f"asunto: {enviados[0][1] if enviados else ''!r}")

    # ---- (f) Anti-abuso ----
    limite = Limitador(max_mensajes=3, ventana_segundos=0.2)
    salidas = [limite.registrar(TELEFONO) for _ in range(5)]
    caso("(f) Anti-abuso: 3 ok, el 4º avisa y el 5º se ignora en silencio",
         salidas == ["ok", "ok", "ok", "avisar", "silencio"],
         f"salidas: {salidas}")
    time.sleep(0.25)
    caso("(f) Anti-abuso: pasada la ventana, vuelve a dejar pasar",
         limite.registrar(TELEFONO) == "ok",
         "siguió bloqueado")
    limite2 = Limitador(max_mensajes=3, ventana_segundos=0.2)
    limite2.registrar("5216694608264")
    caso("(f) Anti-abuso: el límite es por teléfono (otro número no se afecta)",
         limite2.registrar(TELEFONO) == "ok",
         "otro teléfono afectado")

    # ---- Guion: las reglas nuevas están escritas ----
    guion_normal = " ".join(guion().split())
    caso("Guion: dice que solo ofrezca los huecos libres del contexto",
         "solo con los huecos libres que vienen en el contexto" in guion_normal,
         "falta la regla de huecos")
    caso("Guion: dice que pregunte el nombre completo una sola vez",
         "¿Me das tu nombre completo?" in guion_normal,
         "falta la regla del nombre")
    caso("Guion: al agendar pide nombre completo y número para el registro",
         "a qué número registrarlo" in guion_normal,
         "falta la regla de registro")
    caso("Guion: si preguntan qué recibiste, responde con la verdad",
         "Nunca inventes que fue un aviso del sistema" in guion_normal,
         "falta la regla de mensajes no-texto")
    caso("Guion: cliente que vuelve, responde su pregunta primero",
         "responde su pregunta primero" in guion_normal,
         "falta la regla de regreso")
    caso("Guion: aceptación vaga ('en un mes') no pierde la cita",
         "calcula la fecha aproximada" in guion_normal
         and "no dejes pasar la cita" in guion_normal,
         "falta la regla de fecha vaga")
    caso("Guion: el nombre del robot viene de Conocimiento, no se inventa",
         "no inventes un nombre" in guion_normal,
         "falta la regla del nombre")
    caso("Guion: al agendar pide nombre completo aunque el perfil traiga uno",
         "aunque el perfil ya traiga un nombre" in guion_normal,
         "falta la regla de nombre completo al agendar")
    caso("Guion: un agradecimiento no es un sí a agendar",
         "Un agradecimiento no es un sí a agendar" in guion_normal,
         "falta la regla de cortesía tras fallo")
    caso("Guion: al agendar propone con botones, no lista huecos en texto",
         "NO listes los huecos en texto" in guion_normal
         and "marca quiere_agendar con esa fecha_cita" in guion_normal,
         "falta la regla de propuesta con botones")
    caso("Guion: si preguntan por ubicación, manda dirección, horarios y mapa",
         "enlace de mapa" in guion_normal
         and "Nunca inventes un enlace ni una dirección" in guion_normal,
         "falta la regla de ubicación/mapa")
    caso("Guion: si no hay huecos libres, no ofrece cita",
         "no hay huecos libres" in guion_normal,
         "falta la regla de agenda llena")
    caso("Guion: si es urgente o le duele, pasa a una persona",
         "es urgente o que le duele mucho, pasa a una persona" in guion_normal,
         "falta la regla de urgencia")
    caso("Guion: al proponer no pregunta '¿Te agendo?' ni '¿Confirmo?'",
         "¿Te agendo?" in guion_normal
         and "el sistema agrega la confirmación" in guion_normal,
         "falta la regla de no doble pregunta")
    caso("Guion: con propuesta pendiente no manda botones nuevos",
         "sin proponer otra cita ni" in guion_normal
         and "mandar botones nuevos" in guion_normal,
         "falta la regla de propuesta pendiente")
    caso("Guion: playbook de situaciones frecuentes",
         "Playbook: situaciones frecuentes" in guion_normal
         and "hacia dónde llevar la conversación" in guion_normal,
         "falta el playbook")
    caso("Guion: el agente decide partes (1 o varios mensajes)",
         '"partes"' in guion_normal
         and "cada parte es su propio mensaje" in guion_normal,
         "falta la regla de partes")

    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos PASS (test_v3_3)")
    if fallos:
        print("FALLOS:", fallos)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
