"""Pruebas de la versión 3.10, SIN internet.

Reservas para ti y para alguien más (tope 2 por número):
(a) Red de seguridad: "qué días tienes disponibles el martes para mí
    y el miércoles para mi hermana" genera propuesta con botones,
    aunque el agente no marque quiere_agendar.
(b) R8: "Quedamos en que nos vemos el martes..." se corrige cuando
    no hay cita a futuro (aunque haya una cita vieja).
(c) tiene_cita_futura: cita pasada = False; futura o de hoy = True.
(d) Tope: con 2 citas activas en el espejo, no se propone otra.
(e) Dos citas: propuesta con "Confirmar ambas" → confirma las dos.
(f) Tercera persona: la cita se crea con su nombre y la pregunta de
    datos menciona a la otra persona.
(g) cargar_propuestas: filas viejas sin extra_json cargan igual;
    filas con extra_json recuperan la segunda cita.
(h) _normalizar: citas_extra se limpia (máximo 1, con fecha).
(i) Datos de la otra persona que llegan en la respuesta se guardan
    en las Notas del espejo.
(j) _pregunta_datos_citas: textos históricos y combinados.
(k) _quiere_agendar_ya: frases nuevas de agendar.

Uso:  python test_v3_10.py
"""

from datetime import datetime, timezone

import robot.agent as agent_mod
import robot.logic as logic_mod
from robot.agent import RespuestaAgente, _normalizar
from robot.logic import (
    Dependencias,
    _CITAS_PENDIENTES,
    _cita_es_futura,
    _confirmar_cita_propuesta,
    _guardar_datos_paciente,
    _pregunta_datos_citas,
    _quiere_agendar_ya,
    atender_mensaje,
    cargar_propuestas,
)
from robot.revision import revisar_respuesta

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
# hoy; el martes 24 y el miércoles 25 a las 09:00 sí son válidos.
AHORA = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
FECHA_MARTES = "2026-11-24T09:00:00-07:00"
FECHA_MIERCOLES = "2026-11-25T09:00:00-07:00"


class DepsV310(Dependencias):
    """Servicios de mentira para el flujo completo de reserva."""

    def __init__(self, agente_cola=None, espejo_filas=None, cliente=None,
                 huecos=None):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []  # (telefono, texto, botones)
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.espejo = []
        self.notas_updates = []
        self.espejo_filas = list(espejo_filas or [])
        self.cliente = cliente
        self.huecos = huecos if huecos is not None else [FECHA_MARTES, FECHA_MIERCOLES]
        self.alertas_cita = []

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
        if self.agente_cola:
            return self.agente_cola.pop(0)
        return RespuestaAgente(respuesta_texto="Claro, te ayudo.")

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def enviar_botones(self, telefono, texto, botones):
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
        pass

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
        self.espejo.append(fila)
        self.espejo_filas.append(fila)

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None):
        pass

    def leer_citas_espejo(self):
        return list(self.espejo_filas)

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        self.notas_updates.append((telefono, fecha_cita, notas))

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_cita.append((nombre, telefono, motivo))

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha):
        pass

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


# ------------------------------------------------------------------
# (a) Red de seguridad: disponibilidad = agendar
# ------------------------------------------------------------------

def test_red_de_seguridad_disponibilidad():
    tel = "6671110001"
    agente = RespuestaAgente(
        respuesta_texto="¡Con gusto! Para el martes te propongo a las 09:00 "
                        "para tu cambio, y para tu hermana el miércoles a las 09:00.",
        quiere_agendar="no", motivo="cambiar cita propia y agendar para su hermana",
    )
    d = DepsV310(agente_cola=[agente])
    atender_mensaje(d, tel, "Jose", "que días tienes disponibles el martes para mi "
                    "y el miércoles para mi hermana", con_ritmo=False, ahora=AHORA)
    caso("(a) Disponibilidad: se mandaron botones",
         len(d.botones) == 1, f"botones={d.botones}")
    caso("(a) Disponibilidad: quedó propuesta guardada",
         tel in _CITAS_PENDIENTES, f"pendientes={list(_CITAS_PENDIENTES)}")
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (b) R8: afirmación sin cita a futuro
# ------------------------------------------------------------------

def test_r8_afirmacion_sin_cita_futura():
    texto, v = revisar_respuesta(
        "¡Claro que sí! Quedamos en que nos vemos el martes a las 09:00.",
        {"etapa": "pregunto", "tiene_cita": True, "tiene_cita_futura": False,
         "ultimo_mensaje_robot": ""}, telefono="6671110002")
    caso("(b) R8: 'quedamos en que nos vemos el martes' se corrige sin cita futura",
         "R8" in v and "quedamos en que" not in texto.lower(),
         f"texto={texto!r} v={v}")
    texto2, v2 = revisar_respuesta(
        "¡Claro que sí! Quedamos en que nos vemos el martes a las 09:00.",
        {"etapa": "agendado", "tiene_cita": True, "tiene_cita_futura": True,
         "ultimo_mensaje_robot": ""}, telefono="6671110002")
    caso("(b) R8: con cita futura, no se toca",
         v2 == [] and "quedamos en que" in texto2.lower(),
         f"texto={texto2!r} v={v2}")
    texto3, v3 = revisar_respuesta(
        "¡Perfecto! Nos vemos el miércoles entonces.",
        {"etapa": "pregunto", "tiene_cita": False, "tiene_cita_futura": False,
         "ultimo_mensaje_robot": ""}, telefono="6671110002")
    caso("(b) R8: 'nos vemos el miércoles' sin cita se corrige",
         "R8" in v3, f"texto={texto3!r} v={v3}")


# ------------------------------------------------------------------
# (c) tiene_cita_futura
# ------------------------------------------------------------------

def test_cita_es_futura():
    caso("(c) Cita pasada (agendado viejo) → False",
         _cita_es_futura({"fecha_cita": "2026-11-19T09:00:00", "estatus": "agendado"}, AHORA) is False)
    caso("(c) Cita futura → True",
         _cita_es_futura({"fecha_cita": "2026-11-25T09:00:00", "estatus": "agendado"}, AHORA) is True)
    caso("(c) Cita de hoy → True",
         _cita_es_futura({"fecha_cita": "2026-11-22T09:00:00", "estatus": "agendado"}, AHORA) is True)
    caso("(c) Sin cita → False",
         _cita_es_futura({"fecha_cita": "", "estatus": "en conversacion"}, AHORA) is False)
    caso("(c) Sin cliente → False",
         _cita_es_futura(None, AHORA) is False)


# ------------------------------------------------------------------
# (d) Tope de 2 citas por número
# ------------------------------------------------------------------

def test_tope_dos_citas():
    tel = "6671110004"
    espejo = [
        {"Teléfono": tel, "Estado": "Confirmada", "Fecha": "2026-11-24"},
        {"Teléfono": tel, "Estado": "Confirmada", "Fecha": "2026-11-25"},
    ]
    agente = RespuestaAgente(
        respuesta_texto="¡Claro! Te la agendo.",
        quiere_agendar="si", fecha_cita=FECHA_MARTES, motivo="Limpieza dental",
        nombre="Ana",
    )
    d = DepsV310(agente_cola=[agente], espejo_filas=espejo)
    atender_mensaje(d, tel, "Ana", "quiero agendar una cita", con_ritmo=False, ahora=AHORA)
    caso("(d) Tope: no se mandan botones con 2 activas",
         len(d.botones) == 0, f"botones={d.botones}")
    caso("(d) Tope: mensaje explica el límite",
         any("2 citas" in t for _, t in d.textos), f"textos={d.textos}")
    caso("(d) Tope: no quedó propuesta",
         tel not in _CITAS_PENDIENTES)
    _CITAS_PENDIENTES.pop(tel, None)


# ------------------------------------------------------------------
# (e) Dos citas: Confirmar ambas
# ------------------------------------------------------------------

def test_dos_citas_propuesta_y_confirmacion():
    tel = "6671110005"
    agente = RespuestaAgente(
        respuesta_texto="¡Con gusto te ayudo con las dos!",
        quiere_agendar="si", fecha_cita=FECHA_MARTES, motivo="Limpieza dental",
        nombre="Ana",
        citas_extra=[{
            "motivo": "Limpieza dental", "fecha_cita": FECHA_MIERCOLES,
            "nombre_paciente": "", "relacion_paciente": "tu hermana",
        }],
    )
    d = DepsV310(agente_cola=[agente])
    atender_mensaje(d, tel, "Ana", "quiero una cita el martes para mi y el "
                    "miércoles para mi hermana", con_ritmo=False, ahora=AHORA)
    caso("(e) Dos citas: botón 'Confirmar ambas'",
         len(d.botones) == 1 and d.botones[0][2][0] == ("confirmar_cita", "Confirmar ambas"),
         f"botones={d.botones}")
    caso("(e) Dos citas: la propuesta lista ambas",
         "Confirmamos ambas" in d.botones[0][1] and "tu hermana" in d.botones[0][1].lower(),
         f"texto={d.botones[0][1]!r}")
    propuesta = _CITAS_PENDIENTES.get(tel) or {}
    caso("(e) Dos citas: propuesta guardada con cita2",
         bool(propuesta.get("cita2")), f"propuesta={propuesta}")

    # Confirmar las dos.
    d2 = DepsV310()
    r = _confirmar_cita_propuesta(d2, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(e) Dos citas: se crearon 2 citas",
         len(d2.citas) == 2, f"citas={d2.citas}")
    caso("(e) Dos citas: 2 filas en el espejo",
         len(d2.espejo) == 2 and all(f["Estado"] == "Confirmada" for f in d2.espejo),
         f"espejo={d2.espejo}")
    caso("(e) Dos citas: el mensaje lista las dos",
         any("Tu cita quedó" in t and "tu hermana" in t.lower() for _, t in d2.textos),
         f"textos={d2.textos}")
    caso("(e) Dos citas: la pregunta de datos cubre a la hermana",
         any("Para dejarlas bien registradas" in t and "tu hermana" in t.lower()
             for _, t in d2.textos), f"textos={d2.textos}")


# ------------------------------------------------------------------
# (f) Tercera persona: nombre en la cita + pregunta con relación
# ------------------------------------------------------------------

def test_tercera_persona():
    tel = "6671110006"
    _CITAS_PENDIENTES[tel] = {
        "nombre": "Ana", "motivo": "Limpieza dental",
        "fecha_cita": FECHA_MIERCOLES, "fecha_bonita": "miércoles 25 de noviembre a las 09:00",
        "creado_en": "2026-11-22T10:00:00+00:00",
        "nombre_paciente": "María López", "relacion_paciente": "tu hermana",
        "numero_paciente": "", "cita2": None,
    }
    d = DepsV310()
    _confirmar_cita_propuesta(d, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(f) Tercera: la cita se crea con el nombre de la otra persona",
         len(d.citas) == 1 and d.citas[0]["nombre"] == "María López",
         f"citas={d.citas}")
    caso("(f) Tercera: el mensaje dice 'La cita de tu hermana quedó'",
         any("La cita de tu hermana quedó" in t for _, t in d.textos),
         f"textos={d.textos}")
    caso("(f) Tercera: pregunta el número de la hermana",
         any("número registro la cita de tu hermana" in t for _, t in d.textos),
         f"textos={d.textos}")


# ------------------------------------------------------------------
# (g) cargar_propuestas: compatibilidad
# ------------------------------------------------------------------

def test_cargar_propuestas_compatibilidad():
    import json

    class DepsLeer(DepsV310):
        def __init__(self, filas):
            super().__init__()
            self._filas = filas

        def leer_propuestas(self):
            return self._filas

    filas = [
        {"telefono": "6671110007", "nombre": "Ana", "motivo": "Limpieza",
         "fecha_cita": FECHA_MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
         "creado_en": "2026-11-22T10:00:00+00:00"},
        {"telefono": "6671110008", "nombre": "Luis", "motivo": "Revisión",
         "fecha_cita": FECHA_MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
         "creado_en": "2026-11-22T10:00:00+00:00",
         "extra_json": json.dumps({
             "nombre_paciente": "", "relacion_paciente": "tu hijo",
             "numero_paciente": "",
             "cita2": {"motivo": "Limpieza", "fecha_cita": FECHA_MIERCOLES,
                       "fecha_bonita": "miércoles 25 de noviembre a las 09:00",
                       "nombre_paciente": "Pedro", "relacion_paciente": "tu hijo",
                       "numero_paciente": ""},
         })},
    ]
    n = cargar_propuestas(DepsLeer(filas))
    caso("(g) Cargar: recuperó 2 propuestas", n == 2, f"n={n}")
    p1 = _CITAS_PENDIENTES.get("6671110007") or {}
    caso("(g) Cargar: fila vieja sin extra_json → una cita",
         p1.get("cita2") is None and p1.get("nombre_paciente") == "",
         f"p1={p1}")
    p2 = _CITAS_PENDIENTES.get("6671110008") or {}
    caso("(g) Cargar: fila con extra_json → cita2 recuperada",
         bool(p2.get("cita2")) and (p2.get("cita2") or {}).get("nombre_paciente") == "Pedro",
         f"p2={p2}")
    _CITAS_PENDIENTES.pop("6671110007", None)
    _CITAS_PENDIENTES.pop("6671110008", None)


# ------------------------------------------------------------------
# (h) _normalizar: citas_extra limpio
# ------------------------------------------------------------------

def test_normalizar_citas_extra():
    r = _normalizar({
        "respuesta_texto": "ok", "quiere_agendar": "si",
        "citas_extra": [
            {"motivo": "Limpieza", "fecha_cita": FECHA_MIERCOLES,
             "relacion_paciente": "tu hermana"},
            {"motivo": "Otra", "fecha_cita": FECHA_MARTES},
        ],
    })
    caso("(h) Normalizar: máximo 1 extra",
         len(r.citas_extra) == 1, f"extra={r.citas_extra}")
    caso("(h) Normalizar: conserva la primera con fecha",
         r.citas_extra and r.citas_extra[0]["fecha_cita"] == FECHA_MIERCOLES,
         f"extra={r.citas_extra}")
    r2 = _normalizar({"respuesta_texto": "ok", "citas_extra": [{"motivo": "X"}]})
    caso("(h) Normalizar: sin fecha se descarta",
         r2.citas_extra == [], f"extra={r2.citas_extra}")
    r3 = _normalizar({"respuesta_texto": "ok", "citas_extra": "no es lista"})
    caso("(h) Normalizar: no-lista → vacía",
         r3.citas_extra == [], f"extra={r3.citas_extra}")
    r4 = _normalizar({"respuesta_texto": "ok", "nombre_paciente": "María López",
                      "relacion_paciente": "tu hermana", "numero_paciente": "6691234567"})
    caso("(h) Normalizar: datos de la otra persona",
         r4.nombre_paciente == "María López" and r4.relacion_paciente == "tu hermana"
         and r4.numero_paciente == "6691234567",
         f"r={r4}")


# ------------------------------------------------------------------
# (i) Datos de la otra persona → Notas del espejo
# ------------------------------------------------------------------

def test_guardar_datos_paciente():
    tel = "6671110009"
    d = DepsV310(espejo_filas=[
        {"Teléfono": tel, "Estado": "Confirmada", "Fecha": "2026-11-25",
         "Notas": "Paciente: Ana"},
    ])
    _guardar_datos_paciente(d, tel, "María López", "6691234567")
    caso("(i) Datos paciente: se actualizó la cita espejo",
         len(d.notas_updates) == 1 and "María López" in d.notas_updates[0][2],
         f"updates={d.notas_updates}")
    caso("(i) Datos paciente: conserva las notas viejas",
         len(d.notas_updates) == 1 and "Paciente: Ana" in d.notas_updates[0][2],
         f"updates={d.notas_updates}")


# ------------------------------------------------------------------
# (j) _pregunta_datos_citas
# ------------------------------------------------------------------

def test_pregunta_datos():
    p = _pregunta_datos_citas([{"es_tercero": False, "relacion": "la persona",
                                "falta_nombre": True, "falta_numero": True}])
    caso("(j) Pregunta: dueño sin nada (texto histórico)",
         p == "Para dejarte bien registrado, ¿me das tu nombre completo y a qué número lo registro?",
         f"p={p!r}")
    p2 = _pregunta_datos_citas([{"es_tercero": True, "relacion": "tu hermana",
                                 "falta_nombre": True, "falta_numero": True}])
    caso("(j) Pregunta: tercera sin nada",
         "nombre completo de tu hermana" in p2 and "a qué número la registro" in p2,
         f"p={p2!r}")
    p3 = _pregunta_datos_citas([
        {"es_tercero": False, "relacion": "la persona", "falta_nombre": True, "falta_numero": True},
        {"es_tercero": True, "relacion": "tu hermana", "falta_nombre": True, "falta_numero": True},
    ])
    caso("(j) Pregunta: dos citas combinada",
         p3.startswith("Para dejarlas bien registradas") and "tu hermana" in p3,
         f"p={p3!r}")
    p4 = _pregunta_datos_citas([{"es_tercero": False, "relacion": "la persona",
                                 "falta_nombre": False, "falta_numero": False}])
    caso("(j) Pregunta: nada falta → vacía", p4 == "", f"p={p4!r}")


# ------------------------------------------------------------------
# (k) _quiere_agendar_ya
# ------------------------------------------------------------------

def test_quiere_agendar_frases():
    caso("(k) 'qué días tienes disponibles...' → agendar",
         _quiere_agendar_ya("que días tienes disponibles el martes para mi y el miércoles para mi hermana") is True)
    caso("(k) 'quiero agendar para mi hermana' → agendar",
         _quiere_agendar_ya("quiero agendar para mi hermana") is True)
    caso("(k) Pregunta de precio → no agendar",
         _quiere_agendar_ya("¿cuánto cuesta la limpieza?") is False)
    caso("(k) Saludo → no agendar",
         _quiere_agendar_ya("hola buenas tardes") is False)


def main():
    try:
        test_red_de_seguridad_disponibilidad()
        test_r8_afirmacion_sin_cita_futura()
        test_cita_es_futura()
        test_tope_dos_citas()
        test_dos_citas_propuesta_y_confirmacion()
        test_tercera_persona()
        test_cargar_propuestas_compatibilidad()
        test_normalizar_citas_extra()
        test_guardar_datos_paciente()
        test_pregunta_datos()
        test_quiere_agendar_frases()
    finally:
        _CITAS_PENDIENTES.clear()

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
