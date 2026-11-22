"""Pruebas de la versión 3.11, SIN internet.

Reservas robustas (día correcto, memoria sin citas viejas, botones
sin fricción):
(a) _dias_pedidos: días mencionados en orden, con acentos y sin
    falsos positivos dentro de otras palabras.
(b) _relacion_pedida: "para mi hermana" → "hermana"; sin otra
    persona → "".
(c) _hueco_en_dia: primer hueco en el día pedido; None si no hay.
(d) Red de seguridad respeta el día: "el martes para mí y el
    miércoles para mi hermana" propone martes + miércoles (no el
    lunes), con "Confirmar ambas" y sin la lista de horas del agente.
(e) Red de seguridad de un solo día: "quiero una cita el martes"
    propone el martes con texto limpio y botones.
(f) Memoria: una cita pasada ya no cuenta como vigente
    (tiene_cita False, etapa no agendado); una futura sí. Sin
    "ahora" se mantiene el criterio viejo (compatibilidad).
(g) Botones que fallan: el error se registra en Diagnóstico
    (whatsapp FALLO) y el cliente igual recibe el texto.
(h) Cambiar hora con dos citas: la pregunta va con botones
    (cambiar_mia / cambiar_de_otra) y esos botones se atienden.
(i) Contexto: con cita pasada, el agente recibe la línea "ya pasó"
    y el estado dice tiene_cita false.

Uso:  python test_v3_11.py
"""

from datetime import datetime, timezone

from robot.agent import RespuestaAgente
from robot.estado import estado_cliente
from robot.logic import (
    Dependencias,
    _CITAS_PENDIENTES,
    _dias_pedidos,
    _hueco_en_dia,
    _relacion_pedida,
    atender_boton,
    atender_mensaje,
)

RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]

# Domingo 2026-11-22 10:00 UTC (03:00 MST): la clínica está cerrada
# hoy; lunes 23, martes 24 y miércoles 25 a las 09:00 son válidos.
AHORA = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"
PASADA = "2026-11-19T09:00:00-07:00"


class DepsV311(Dependencias):
    """Servicios de mentira para el flujo completo de reserva.

    Ojo: proximos_huecos_libres usa la firma vieja (sin cantidad/dias)
    a propósito: prueba que el llamado amplio cae bien al llamado de
    siempre con los fakes viejos.
    """

    def __init__(self, agente_cola=None, cliente=None, huecos=None,
                 botones_fallan=False):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []  # (telefono, texto, botones)
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.diagnosticos = []
        self.cliente = cliente
        self.huecos = huecos if huecos is not None else [LUNES, MARTES, MIERCOLES]
        self.botones_fallan = botones_fallan
        self.ultimo_mensaje_agente = ""

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return self.cliente

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return []

    def leer_historial(self, telefono):
        return []

    def leer_propuestas(self):
        return []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.ultimo_mensaje_agente = mensaje
        if self.agente_cola:
            return self.agente_cola.pop(0)
        return RespuestaAgente(respuesta_texto="Claro, te ayudo.")

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def enviar_botones(self, telefono, texto, botones):
        if self.botones_fallan:
            raise Exception("WhatsApp devolvió 400: prueba simulada")
        self.botones.append((telefono, texto, botones))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"quien": quien, "mensaje": mensaje, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"nombre": nombre, "telefono": telefono, "motivo": motivo,
                              "fecha_cita": fecha_cita, "estatus": estatus})

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append({"componente": componente, "estado": estado,
                                  "detalle": detalle, "telefono": telefono,
                                  "contexto": contexto})

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def proximos_huecos_libres(self, conocimiento, ahora):
        return list(self.huecos)

    def hora_libre(self, fecha_iso):
        return True

    def duracion_servicio(self, motivo):
        return None

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        cita = {"nombre": nombre, "telefono": telefono, "motivo": motivo,
                "fecha_cita": fecha_cita, "nota": nota}
        self.citas.append(cita)
        return cita

    def registrar_cita_espejo(self, fila):
        pass

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None):
        pass

    def leer_citas_espejo(self):
        return []

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha):
        pass

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


# ------------------------------------------------------------------
# (a) _dias_pedidos
# ------------------------------------------------------------------

def test_dias_pedidos():
    caso("(a) Dos días en orden",
         _dias_pedidos("el martes para mí y el miércoles para mi hermana") == [1, 2])
    caso("(a) Un día con acento",
         _dias_pedidos("quiero una cita el miércoles") == [2])
    caso("(a) Sin días", _dias_pedidos("hola buenas tardes") == [])
    caso("(a) Orden de aparición, no de la semana",
         _dias_pedidos("el viernes o mejor el lunes") == [4, 0])
    caso("(a) Día repetido cuenta una vez",
         _dias_pedidos("el martes y otra vez el martes") == [1])
    caso("(a) Sin falsos positivos dentro de palabras",
         _dias_pedidos("martesito") == [])


# ------------------------------------------------------------------
# (b) _relacion_pedida
# ------------------------------------------------------------------

def test_relacion_pedida():
    caso("(b) Hermana", _relacion_pedida("una cita para mi hermana") == "hermana")
    caso("(b) Sin otra persona", _relacion_pedida("quiero una cita") == "")
    caso("(b) Mamá con acento", _relacion_pedida("para mi mamá") == "mama")


# ------------------------------------------------------------------
# (c) _hueco_en_dia
# ------------------------------------------------------------------

def test_hueco_en_dia():
    huecos = [LUNES, MARTES, MIERCOLES]
    caso("(c) Encuentra el martes", _hueco_en_dia(huecos, 1, AHORA) == MARTES)
    caso("(c) Encuentra el miércoles", _hueco_en_dia(huecos, 2, AHORA) == MIERCOLES)
    caso("(c) Sábado sin hueco → None", _hueco_en_dia(huecos, 5, AHORA) is None)
    caso("(c) Lista vacía → None", _hueco_en_dia([], 1, AHORA) is None)


# ------------------------------------------------------------------
# (d) Red de seguridad respeta los días (dos citas)
# ------------------------------------------------------------------

def test_red_seguridad_dos_dias():
    tel = "6671111001"
    agente = RespuestaAgente(
        respuesta_texto="¡Hola! El martes y el miércoles solo tenemos "
                        "disponibles a las 09:00 y a las 10:00. "
                        "¿Quieres cambiar alguna de tus horas?",
        quiere_agendar="no", motivo="Consulta de disponibilidad",
    )
    d = DepsV311(agente_cola=[agente])
    atender_mensaje(d, tel, "Jose",
                    "que días tienes disponibles el martes para mi y el "
                    "miércoles para mi hermana",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(tel) or {}
    caso("(d) Se mandaron botones", len(d.botones) == 1, f"botones={d.botones}")
    caso("(d) La primera cita es el MARTES (no el lunes)",
         str(propuesta.get("fecha_cita", "")).startswith("2026-11-24"),
         f"fecha={propuesta.get('fecha_cita')}")
    cita2 = propuesta.get("cita2") or {}
    caso("(d) La segunda cita es el MIÉRCOLES",
         str(cita2.get("fecha_cita", "")).startswith("2026-11-25"),
         f"cita2={cita2}")
    caso("(d) La segunda cita es para la hermana",
         cita2.get("relacion_paciente") == "hermana", f"cita2={cita2}")
    if d.botones:
        ids = [b[0] for b in d.botones[0][2]]
        caso("(d) Botón 'Confirmar ambas'", "confirmar_cita" in ids, f"ids={ids}")
        texto_enviado = d.botones[0][1]
        caso("(d) El texto NO lista horas del agente",
             "solo tenemos disponibles" not in texto_enviado
             and "¿Quieres cambiar" not in texto_enviado,
             f"texto={texto_enviado!r}")
        caso("(d) El texto propone las dos citas",
             "martes 24" in texto_enviado and "miércoles 25" in texto_enviado,
             f"texto={texto_enviado!r}")
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (e) Red de seguridad de un solo día: texto limpio
# ------------------------------------------------------------------

def test_red_seguridad_un_dia():
    tel = "6671111002"
    agente = RespuestaAgente(
        respuesta_texto="Claro, te propongo el martes a las 9 y a las 10, "
                        "¿te parece?",
        quiere_agendar="no", motivo="limpieza",
    )
    d = DepsV311(agente_cola=[agente])
    atender_mensaje(d, tel, "Jose", "quiero una cita el martes",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(tel) or {}
    caso("(e) La cita propuesta es el MARTES",
         str(propuesta.get("fecha_cita", "")).startswith("2026-11-24"),
         f"fecha={propuesta.get('fecha_cita')}")
    caso("(e) Se mandaron botones", len(d.botones) == 1, f"botones={d.botones}")
    if d.botones:
        texto_enviado = d.botones[0][1]
        caso("(e) Texto limpio sin la lista de horas del agente",
             "a las 9 y a las 10" not in texto_enviado
             and "¿La confirmamos?" in texto_enviado,
             f"texto={texto_enviado!r}")
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (f) Memoria: cita pasada no es vigente
# ------------------------------------------------------------------

def test_memoria_cita_pasada():
    cliente_pasada = {"fecha_cita": PASADA, "estatus": "agendado"}
    cliente_futura = {"fecha_cita": MIERCOLES, "estatus": "agendado"}
    e1 = estado_cliente([], None, cliente_pasada, "", ahora=AHORA)
    caso("(f) Cita pasada: tiene_cita False", e1["tiene_cita"] is False,
         f"estado={e1}")
    caso("(f) Cita pasada: etapa no es agendado", e1["etapa"] != "agendado",
         f"etapa={e1['etapa']}")
    e2 = estado_cliente([], None, cliente_futura, "", ahora=AHORA)
    caso("(f) Cita futura: tiene_cita True", e2["tiene_cita"] is True,
         f"estado={e2}")
    caso("(f) Cita futura: etapa agendado", e2["etapa"] == "agendado",
         f"etapa={e2['etapa']}")
    e3 = estado_cliente([], None, cliente_pasada, "")
    caso("(f) Sin 'ahora' se mantiene el criterio viejo (compat)",
         e3["tiene_cita"] is True, f"estado={e3}")


# ------------------------------------------------------------------
# (g) Botones que fallan: se registra y el cliente recibe texto
# ------------------------------------------------------------------

def test_botones_fallan_se_registra():
    tel = "6671111003"
    agente = RespuestaAgente(
        respuesta_texto="Perfecto, te agendo.", quiere_agendar="si",
        fecha_cita=MARTES, motivo="limpieza",
    )
    d = DepsV311(agente_cola=[agente], botones_fallan=True)
    r = atender_mensaje(d, tel, "Jose", "quiero una cita el martes",
                        con_ritmo=False, ahora=AHORA)
    fallos = [x for x in d.diagnosticos
              if x["componente"] == "whatsapp" and x["estado"] == "FALLO"]
    caso("(g) El fallo de botones se registró en Diagnóstico",
         len(fallos) == 1, f"diagnosticos={d.diagnosticos}")
    caso("(g) El detalle trae el error de Meta",
         bool(fallos) and "Botones no enviados" in fallos[0]["detalle"],
         f"fallos={fallos}")
    caso("(g) El cliente igual recibió el texto (nunca sin respuesta)",
         any("martes 24" in t for _, t in d.textos), f"textos={d.textos}")
    caso("(g) La propuesta sigue viva para confirmar por texto",
         r.get("cita_propuesta") is True, f"r={r}")
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (h) Cambiar hora con dos citas: botones
# ------------------------------------------------------------------

def test_cambiar_hora_con_botones():
    tel = "6671111004"
    _CITAS_PENDIENTES[tel] = {
        "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
        "cita2": {"fecha_cita": MIERCOLES,
                  "fecha_bonita": "miércoles 25 de noviembre a las 09:00",
                  "relacion_paciente": "hermana"},
    }
    d = DepsV311()
    atender_boton(d, tel, "Jose", "cambiar_hora", con_ritmo=False, ahora=AHORA)
    caso("(h) La pregunta de cuál cambiar va con botones",
         len(d.botones) == 1, f"botones={d.botones}")
    if d.botones:
        ids = [b[0] for b in d.botones[0][2]]
        caso("(h) Botones: la mía / la de hermana / persona",
             ids == ["cambiar_mia", "cambiar_de_otra", "hablar_persona"],
             f"ids={ids}")
    # El cliente toca "La mía": se le pregunta el nuevo día/hora.
    d.textos.clear()
    r = atender_boton(d, tel, "Jose", "cambiar_mia", con_ritmo=False, ahora=AHORA)
    caso("(h) Tocar 'La mía' pregunta el nuevo día/hora",
         r.get("respondio") is True
         and any("para la tuya" in t for _, t in d.textos),
         f"textos={d.textos} r={r}")
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (i) Contexto: cita pasada se marca como pasada para el agente
# ------------------------------------------------------------------

def test_contexto_cita_pasada():
    tel = "6671111005"
    cliente = {"fecha_cita": PASADA, "estatus": "agendado", "nombre": "Jose"}
    d = DepsV311(cliente=cliente)
    atender_mensaje(d, tel, "Jose", "hola", con_ritmo=False, ahora=AHORA)
    msg = d.ultimo_mensaje_agente
    caso("(i) El contexto dice que la cita ya pasó",
         "ya pasó" in msg, f"msg={msg[:400]!r}")
    caso("(i) El estado dice tiene_cita false",
         '"tiene_cita": false' in msg, f"msg={msg[:400]!r}")
    _CITAS_PENDIENTES.pop(tel, None)


if __name__ == "__main__":
    test_dias_pedidos()
    test_relacion_pedida()
    test_hueco_en_dia()
    test_red_seguridad_dos_dias()
    test_red_seguridad_un_dia()
    test_memoria_cita_pasada()
    test_botones_fallan_se_registra()
    test_cambiar_hora_con_botones()
    test_contexto_cita_pasada()
    total = len(RESULTADOS)
    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{total} pruebas pasaron")
    raise SystemExit(0 if pasaron == total else 1)
