"""Pruebas de la v3.13 (Cita urgente: urgencia con oferta de cita,
marca URGENTE en el CRM y correo con el porqué).

(a) Urgencia fuera de horario: mensaje con empatía + advertencia de
    horario, propuesta urgente guardada con la razón, botones
    después del handoff, agente no llamado.
(b) Urgencia en horario: sin advertencia de fuera de horario, la
    propuesta también se ofrece.
(c) Confirmar la cita urgente: espejo con Urgencia=SI y URGENTE en
    Notas, nota del calendario con URGENTE, correo urgente con el
    porqué (y NO el correo normal).
(d) Cita normal: Urgencia=NO y correo normal, sin correo urgente.
(e) Urgencia con alertas_instantaneas=NO: el correo urgente sale
    igual (una urgencia no espera al lunes).
(f) Urgencia sin huecos: sin propuesta ni botones, handoff igual.
(g) Urgencia con propuesta previa: no se pisa la propuesta viva.
(h) Urgencia con agenda apagada: sin propuesta, handoff igual.
(i) extra_json: la urgencia sobrevive al reinicio (guardar → leer)
    y las propuestas viejas siguen cargando.
(j) _fila_espejo: Urgencia SI/NO y Notas con el porqué.
(k) mail.alerta_cita_urgente: asunto y cuerpo con 🚨 y la razón.
(l) sheets._CITAS_COLUMNAS: 16 columnas, la última es Urgencia.
(m) Urgencia con profesional: la oferta lleva "con la Dra. Ruiz".

Sin internet: todo con fakes y parches, como las demás pruebas.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import robot.mail as mail_mod
import robot.negocio as negocio_mod
import robot.sheets as sheets_mod
from robot.agent import RespuestaAgente
from robot.logic import (
    Dependencias,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _extra_propuesta_json,
    _fila_espejo,
    _parse_extra_propuesta,
    atender_boton,
    atender_mensaje,
    cargar_propuestas,
)

TEL = "5216694608263"
# Domingo 2026-11-22 10:00 UTC (03:00 MST): clínica cerrada.
AHORA_CERRADO = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
# Lunes 2026-11-23 17:00 UTC (10:00 MST): clínica abierta.
AHORA_ABIERTO = datetime(2026, 11, 23, 17, 0, tzinfo=timezone.utc)
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]

TOTAL = [0]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    TOTAL[0] += 1
    if condicion:
        print(f"  ok  {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"FALLA {nombre} :: {detalle}")


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()


class DepsV313(Dependencias):
    """Servicios de mentira para el flujo de cita urgente."""

    def __init__(self, huecos=None, huecos_pro=None, agente_cola=None):
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
        self.huecos = huecos if huecos is not None else [MARTES, MIERCOLES]
        self.huecos_pro = huecos_pro if huecos_pro is not None else []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return None

    def leer_conocimiento(self):
        return CONOCIMIENTO

    def leer_fotos(self):
        return []

    def leer_historial(self, telefono):
        return []

    def leer_propuestas(self):
        return []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_al_agente.append(mensaje)
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
        self.diagnosticos.append({"componente": componente, "estado": estado,
                                  "detalle": detalle, "telefono": telefono})

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def proximos_huecos_libres(self, conocimiento, ahora, cantidad=2, dias=3):
        return list(self.huecos)

    def proximos_huecos_profesionales(self, conocimiento, ahora, cantidad=2, dias=3):
        return list(self.huecos_pro)

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
        self.mirror.append(fila)

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None,
                               recordatorio_enviado=None, urgencia=None):
        pass

    def leer_citas_espejo(self):
        return []

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

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
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


def _urgencia(d, ahora=AHORA_CERRADO):
    limpiar()
    return atender_mensaje(d, TEL, "Jose Ramon", "me duele mucho la muela, es urgente",
                           con_ritmo=False, ahora=ahora)


# ------------------------------------------------------------------
# (a) Urgencia fuera de horario: mensaje + propuesta + botones
# ------------------------------------------------------------------

def test_a_urgencia_fuera_de_horario():
    d = DepsV313()
    r = _urgencia(d)
    texto = d.textos[0][1] if d.textos else ""
    caso("(a) Urgencia: handoff sin llamar al agente",
         r.get("handoff") is True and len(d.mensajes_al_agente) == 0, f"{r}")
    caso("(a) Urgencia: guía de atención inmediata",
         "busca atención inmediata" in texto, texto)
    caso("(a) Urgencia fuera de horario: advierte con empatía",
         "fuera de horario" in texto and "en cuanto abran" in texto, texto)
    caso("(a) Urgencia: avisa al dueño por handoff",
         len(d.alertas_handoff) == 1, f"{d.alertas_handoff}")
    propuesta = _CITAS_PENDIENTES.get(TEL)
    caso("(a) Urgencia: propuesta guardada con la razón",
         bool(propuesta) and "Urgencia" in str(propuesta.get("urgencia", "")),
         f"{propuesta}")
    caso("(a) Urgencia: botones de cita enviados después del handoff",
         len(d.botones) == 1 and d.botones[0][2][0][0] == "confirmar_cita",
         f"{d.botones}")
    caso("(a) Urgencia: la oferta propone la primera hora",
         d.botones and "Te propongo tu cita" in d.botones[0][1], f"{d.botones}")
    limpiar()


# ------------------------------------------------------------------
# (b) Urgencia en horario: sin advertencia, con propuesta
# ------------------------------------------------------------------

def test_b_urgencia_en_horario():
    d = DepsV313()
    _urgencia(d, ahora=AHORA_ABIERTO)
    texto = d.textos[0][1] if d.textos else ""
    caso("(b) Urgencia en horario: sin advertencia de fuera de horario",
         "fuera de horario" not in texto, texto)
    caso("(b) Urgencia en horario: propuesta ofrecida igual",
         len(d.botones) == 1 and TEL in _CITAS_PENDIENTES, f"{d.botones}")
    limpiar()


# ------------------------------------------------------------------
# (c) Confirmar la cita urgente: CRM + calendario + correo urgente
# ------------------------------------------------------------------

def test_c_confirmar_cita_urgente():
    d = DepsV313()
    _urgencia(d)
    r = atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                      con_ritmo=False, ahora=AHORA_CERRADO)
    caso("(c) Confirmar urgente: cita creada",
         r.get("cita") is not None and len(d.citas) == 1, f"{r} {d.citas}")
    fila = d.mirror[0] if d.mirror else {}
    caso("(c) Confirmar urgente: espejo Urgencia=SI",
         fila.get("Urgencia") == "SI", f"{fila}")
    caso("(c) Confirmar urgente: Notas con el porqué",
         "URGENTE" in str(fila.get("Notas", "")), f"{fila}")
    caso("(c) Confirmar urgente: calendario con URGENTE",
         d.citas and "URGENTE" in d.citas[0]["nota"], f"{d.citas}")
    caso("(c) Confirmar urgente: correo urgente con razón",
         len(d.alertas_urgentes) == 1
         and "Urgencia" in d.alertas_urgentes[0]["razon"], f"{d.alertas_urgentes}")
    caso("(c) Confirmar urgente: NO manda el correo normal",
         len(d.alertas_confirmadas) == 0, f"{d.alertas_confirmadas}")
    limpiar()


# ------------------------------------------------------------------
# (d) Cita normal: Urgencia=NO, correo normal
# ------------------------------------------------------------------

def test_d_cita_normal():
    limpiar()
    d = DepsV313()
    _CITAS_PENDIENTES[TEL] = {
        "nombre": "Jose Ramon", "motivo": "Limpieza",
        "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
        "creado_en": AHORA_ABIERTO.isoformat(), "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "", "numero_paciente": "",
        "cita2": None,
    }
    atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                      con_ritmo=False, ahora=AHORA_ABIERTO)
    fila = d.mirror[0] if d.mirror else {}
    caso("(d) Cita normal: espejo Urgencia=NO",
         fila.get("Urgencia") == "NO", f"{fila}")
    caso("(d) Cita normal: correo normal, sin urgente",
         len(d.alertas_confirmadas) == 1 and len(d.alertas_urgentes) == 0,
         f"{d.alertas_confirmadas} {d.alertas_urgentes}")
    caso("(d) Cita normal: sin URGENTE en la nota",
         d.citas and "URGENTE" not in d.citas[0]["nota"], f"{d.citas}")
    limpiar()


# ------------------------------------------------------------------
# (e) Urgencia con alertas_instantaneas=NO: el urgente sale igual
# ------------------------------------------------------------------

def test_e_urgente_sin_alertas_instantaneas():
    orig = negocio_mod.configuracion
    try:
        negocio_mod.configuracion = lambda: {"alertas_instantaneas": "NO"}
        d = DepsV313()
        _urgencia(d)
        atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                      con_ritmo=False, ahora=AHORA_CERRADO)
        caso("(e) Urgente con alertas NO: el correo urgente sale igual",
             len(d.alertas_urgentes) == 1 and len(d.alertas_confirmadas) == 0,
             f"{d.alertas_urgentes} {d.alertas_confirmadas}")
    finally:
        negocio_mod.configuracion = orig
    limpiar()


# ------------------------------------------------------------------
# (f) Urgencia sin huecos: sin propuesta, handoff igual
# ------------------------------------------------------------------

def test_f_sin_huecos():
    d = DepsV313(huecos=[])
    r = _urgencia(d)
    caso("(f) Sin huecos: handoff igual, sin botones",
         r.get("handoff") is True and len(d.botones) == 0
         and TEL not in _CITAS_PENDIENTES, f"{r} {d.botones}")
    limpiar()


# ------------------------------------------------------------------
# (g) Urgencia con propuesta previa: no se pisa
# ------------------------------------------------------------------

def test_g_propuesta_previa():
    limpiar()
    d = DepsV313()
    previa = {
        "nombre": "Jose Ramon", "motivo": "Limpieza",
        "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
        "creado_en": AHORA_CERRADO.isoformat(), "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "", "numero_paciente": "",
        "cita2": None,
    }
    _CITAS_PENDIENTES[TEL] = previa
    # Sin _urgencia(): ese helper limpia las propuestas.
    r = atender_mensaje(d, TEL, "Jose Ramon", "me duele mucho la muela, es urgente",
                        con_ritmo=False, ahora=AHORA_CERRADO)
    caso("(g) Propuesta previa: no se pisa y no salen botones nuevos",
         r.get("handoff") is True and len(d.botones) == 0
         and _CITAS_PENDIENTES.get(TEL) is previa, f"{r} {d.botones}")
    limpiar()


# ------------------------------------------------------------------
# (h) Urgencia con agenda apagada: sin propuesta
# ------------------------------------------------------------------

def test_h_agenda_apagada():
    orig = negocio_mod.configuracion
    try:
        negocio_mod.configuracion = lambda: {"agendar": "NO"}
        d = DepsV313()
        r = _urgencia(d)
        caso("(h) Agenda apagada: handoff sin propuesta ni botones",
             r.get("handoff") is True and len(d.botones) == 0
             and TEL not in _CITAS_PENDIENTES, f"{r}")
    finally:
        negocio_mod.configuracion = orig
    limpiar()


# ------------------------------------------------------------------
# (i) extra_json: la urgencia sobrevive al reinicio
# ------------------------------------------------------------------

def test_i_extra_json_urgencia():
    propuesta = {
        "nombre": "Ana", "motivo": "me duele", "fecha_cita": MARTES,
        "fecha_bonita": "martes 24 de noviembre a las 09:00",
        "creado_en": AHORA_CERRADO.isoformat(), "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "", "numero_paciente": "",
        "cita2": None, "urgencia": "Urgencia del cliente: me duele mucho",
    }
    extra = _extra_propuesta_json(propuesta)
    caso("(i) extra_json trae la urgencia",
         "Urgencia del cliente" in extra, extra)
    leido = _parse_extra_propuesta(extra)
    caso("(i) parse restaura la urgencia",
         leido.get("urgencia") == "Urgencia del cliente: me duele mucho", f"{leido}")
    vacio = _parse_extra_propuesta("")
    caso("(i) Propuesta vieja (sin extra) carga con urgencia vacía",
         vacio.get("urgencia") == "" and vacio.get("cita2") is None, f"{vacio}")

    limpiar()
    d = DepsV313()

    def leer_con_urgencia():
        return [{
            "telefono": TEL, "nombre": "Ana", "motivo": "me duele",
            "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
            "creado_en": AHORA_CERRADO.isoformat(), "extra_json": extra,
        }]

    d.leer_propuestas = leer_con_urgencia
    n = cargar_propuestas(d)
    recuperada = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(i) cargar_propuestas restaura la urgencia",
         n == 1 and recuperada.get("urgencia") == "Urgencia del cliente: me duele mucho",
         f"{n} {recuperada}")
    limpiar()


# ------------------------------------------------------------------
# (j) _fila_espejo: Urgencia SI/NO y Notas
# ------------------------------------------------------------------

def test_j_fila_espejo():
    base = {"motivo": "Limpieza", "fecha_cita": MARTES,
            "fecha_bonita": "martes 24 de noviembre a las 09:00"}
    normal = _fila_espejo(base, TEL, "Jose Ramon", 60, "Confirmada", "2026-11-22")
    urgente = _fila_espejo(base, TEL, "Jose Ramon", 60, "Confirmada", "2026-11-22",
                           urgencia="Urgencia del cliente: me duele mucho")
    caso("(j) Fila normal: Urgencia=NO, sin URGENTE en Notas",
         normal.get("Urgencia") == "NO" and "URGENTE" not in normal.get("Notas", ""),
         f"{normal}")
    caso("(j) Fila urgente: Urgencia=SI y Notas con el porqué",
         urgente.get("Urgencia") == "SI"
         and "URGENTE: Urgencia del cliente: me duele mucho" in urgente.get("Notas", ""),
         f"{urgente}")


# ------------------------------------------------------------------
# (k) mail.alerta_cita_urgente: asunto y cuerpo
# ------------------------------------------------------------------

def test_k_correo_urgente():
    correos = []
    original = mail_mod.enviar_correo
    try:
        mail_mod.enviar_correo = lambda dest, asunto, cuerpo, html=None: correos.append((dest, asunto, cuerpo))
        mail_mod.alerta_cita_urgente("Ana", "5211", "me duele la muela",
                                     "martes 24 de noviembre a las 09:00",
                                     "2026-11-22T10:00:00",
                                     razon="Urgencia del cliente: me duele mucho la muela")
    finally:
        mail_mod.enviar_correo = original
    caso("(k) Correo urgente: asunto con 🚨 y 'cita con urgencia'",
         correos and "🚨" in correos[0][1] and "cita con urgencia" in correos[0][1].lower(),
         f"{correos}")
    caso("(k) Correo urgente: el cuerpo trae el porqué",
         correos and "me duele mucho la muela" in correos[0][2], f"{correos}")


# ------------------------------------------------------------------
# (l) Columnas del espejo: 16, la última Urgencia
# ------------------------------------------------------------------

def test_l_columnas():
    caso("(l) Citas tiene 16 columnas y la última es Urgencia",
         len(sheets_mod._CITAS_COLUMNAS) == 16
         and sheets_mod._CITAS_COLUMNAS[-1] == "Urgencia",
         f"{sheets_mod._CITAS_COLUMNAS}")


# ------------------------------------------------------------------
# (m) Urgencia con profesional: la oferta lleva el nombre
# ------------------------------------------------------------------

def test_m_urgencia_con_profesional():
    d = DepsV313(huecos_pro=[{"inicio": MARTES, "profesional": "Dra. Ruiz"}])
    _urgencia(d)
    mensaje = d.botones[0][1] if d.botones else ""
    caso("(m) Urgencia con profesional: la oferta dice con quién",
         "Dra. Ruiz" in mensaje, mensaje)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(m) Urgencia con profesional: la propuesta guarda el nombre",
         propuesta.get("profesional") == "Dra. Ruiz", f"{propuesta}")
    limpiar()


def main():
    test_a_urgencia_fuera_de_horario()
    test_b_urgencia_en_horario()
    test_c_confirmar_cita_urgente()
    test_d_cita_normal()
    test_e_urgente_sin_alertas_instantaneas()
    test_f_sin_huecos()
    test_g_propuesta_previa()
    test_h_agenda_apagada()
    test_i_extra_json_urgencia()
    test_j_fila_espejo()
    test_k_correo_urgente()
    test_l_columnas()
    test_m_urgencia_con_profesional()
    print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} casos ok")
    if FALLOS:
        print("FALLARON:", ", ".join(FALLOS))
        sys.exit(1)


if __name__ == "__main__":
    main()
