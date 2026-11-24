"""Pruebas de la v3.12 (Sereno completo: agenda por profesional,
recordatorios, urgencia con guía, handoff con contexto, servicios
sin evasión y confirmaciones en el reporte).

(a) _parse_rango_horas + leer_profesionales: horarios legibles,
    inactivos fuera, domingo cerrado.
(b) proximos_huecos_por_profesional: solo dentro del horario de
    cada profesional, ordenados, con busy que bloquea.
(c) Flujo completo con profesional: la propuesta dice "con la Dra.
    Ruiz", la cita lleva el profesional en la nota y el espejo.
(d) Sin agenda por profesional: todo igual que siempre (fallback).
(e) Urgencia: la IA compone la respuesta, el código fuerza el
    handoff y ofrece la cita con botones.
(f) Correo de handoff con resumen de la conversación.
(g) Recordatorios: manda solo las citas en ventana ~24 h, marca
    Recordatorio_enviado, y el fallo queda en Diagnóstico.
(h) Confirmación de asistencia: "confirmo" con cita futura se
    registra y se responde; sin cita, va al agente.
(i) Reporte semanal: cuenta las confirmaciones de asistencia.
(j) cargar_propuestas: el profesional sobrevive al reinicio
    (extra_json) y las propuestas viejas siguen cargando.
(k) Retomar tras cambiar hora con dos citas: la cita que NO se
    cambia viaja junto con la nueva ("Confirmar ambas"), con
    etiquetas correctas en ambos sentidos; vencida no se adjunta;
    sin propuesta guardada se comporta como antes; hablar con
    persona limpia el retomar.

Sin internet: todo con fakes y parches, como las demás pruebas.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import robot.booking as booking_mod
import robot.logic as logic_mod
import robot.mail as mail_mod
import robot.negocio as negocio_mod
import robot.recordatorios as rec_mod
import robot.report as report_mod
import robot.sheets as sheets_mod
from robot.agent import RespuestaAgente
from robot.logic import (
    Dependencias,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_confirmacion_asistencia,
    atender_boton,
    atender_mensaje,
    cargar_propuestas,
)

TEL = "5216694608263"
# Domingo 2026-11-22 10:00 UTC (03:00 MST): la clínica está cerrada
# hoy; lunes 23, martes 24 y miércoles 25 a las 09:00 son válidos.
AHORA = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"
JUEVES = "2026-11-26T09:00:00-07:00"

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


class DepsV312(Dependencias):
    """Servicios de mentira con agenda por profesional y espejo."""

    def __init__(self, agente_cola=None, cliente=None, huecos_pro=None,
                 espejo=None, plantilla_falla=False):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.mirror = []
        self.diagnosticos = []
        self.plantillas = []
        self.actualizaciones = []
        self.alertas_handoff = []
        self.cliente = cliente
        self.huecos_pro = huecos_pro if huecos_pro is not None else []
        self.espejo = espejo if espejo is not None else []
        self.plantilla_falla = plantilla_falla
        self.mensajes_al_agente = []
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
        self.mensajes_al_agente.append(mensaje)
        self.ultimo_mensaje_agente = mensaje
        if self.agente_cola:
            return self.agente_cola.pop(0)
        return RespuestaAgente(respuesta_texto="Claro, te ayudo.")

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, texto, botones))

    def enviar_plantilla(self, telefono, plantilla, idioma, parametros):
        if self.plantilla_falla:
            raise Exception("WhatsApp devolvió 400: plantilla no aprobada")
        self.plantillas.append((telefono, plantilla, idioma, parametros))

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
                                proxima_accion="", preferencias="", miedos=""):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def proximos_huecos_libres(self, conocimiento, ahora, cantidad=2, dias=3):
        return [MARTES, MIERCOLES]

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
                               recordatorio_enviado=None, urgencia=None,
                               nueva_fecha=None, nueva_hora_inicio=None,
                               nueva_hora_fin=None):
        self.actualizaciones.append({"telefono": telefono, "fecha_cita": fecha_cita,
                                     "estado": estado, "notas": notas,
                                     "recordatorio_enviado": recordatorio_enviado,
                                     "urgencia": urgencia, "nueva_fecha": nueva_fecha,
                                     "nueva_hora_inicio": nueva_hora_inicio,
                                     "nueva_hora_fin": nueva_hora_fin})

    def leer_citas_espejo(self):
        return list(self.espejo)

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha, resumen="", hilo=""):
        self.alertas_handoff.append({"nombre": nombre, "telefono": telefono,
                                     "motivo": motivo, "resumen": resumen})

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


# ------------------------------------------------------------------
# (a) Horarios de profesionales desde la hoja
# ------------------------------------------------------------------

def test_a_profesionales():
    caso("(a) Rango 09:00-18:00",
         sheets_mod._parse_rango_horas("09:00-18:00") == (540, 1080))
    caso("(a) Rango con hora de un dígito",
         sheets_mod._parse_rango_horas("9:00-14:00") == (540, 840))
    caso("(a) Cerrado no es rango",
         sheets_mod._parse_rango_horas("Cerrado") is None)
    caso("(a) Vacío no es rango",
         sheets_mod._parse_rango_horas("") is None)
    caso("(a) Rango invertido no es rango",
         sheets_mod._parse_rango_horas("18:00-09:00") is None)

    original = sheets_mod.leer_pestana
    try:
        sheets_mod.leer_pestana = lambda tab, spreadsheet_id=None: [
            {"Nombre": "Dra. Ruiz", "Especialidad": "Odontología general",
             "Horario_lun_vie": "09:00-18:00", "Horario_sab": "09:00-14:00",
             "Activo": "Sí", "Nota": ""},
            {"Nombre": "Dr. Santos", "Especialidad": "Ortodoncia",
             "Horario_lun_vie": "10:00-18:00", "Horario_sab": "Cerrado",
             "Activo": "Sí", "Nota": ""},
            {"Nombre": "Inactivo", "Especialidad": "X",
             "Horario_lun_vie": "09:00-18:00", "Horario_sab": "09:00-14:00",
             "Activo": "No", "Nota": ""},
            {"Nombre": "Sin horario", "Especialidad": "X",
             "Horario_lun_vie": "Cerrado", "Horario_sab": "Cerrado",
             "Activo": "Sí", "Nota": ""},
        ]
        profs = sheets_mod.leer_profesionales()
    finally:
        sheets_mod.leer_pestana = original
    caso("(a) Solo activos con horario legible",
         [p["nombre"] for p in profs] == ["Dra. Ruiz", "Dr. Santos"],
         f"{profs}")
    caso("(a) Lunes a viernes para los 5 días",
         profs[0]["horarios"].get(0) == (540, 1080)
         and profs[0]["horarios"].get(4) == (540, 1080),
         f"{profs[0]}")
    caso("(a) Sábado cerrado no aparece",
         5 not in profs[1]["horarios"], f"{profs[1]}")
    caso("(a) Domingo siempre cerrado",
         6 not in profs[0]["horarios"] and 6 not in profs[1]["horarios"])
    try:
        def _falla(tab, spreadsheet_id=None):
            raise RuntimeError("sin pestaña")
        sheets_mod.leer_pestana = _falla
        sin_pestana = sheets_mod.leer_profesionales()
    finally:
        sheets_mod.leer_pestana = original
    caso("(a) Sin pestaña devuelve lista vacía (agenda por clínica)",
         sin_pestana == [], f"{sin_pestana}")


# ------------------------------------------------------------------
# (b) Huecos por profesional con calendario de mentira
# ------------------------------------------------------------------

class _ServicioCalFalso:
    def __init__(self, busy):
        self._busy = busy

    def freebusy(self):
        servicio = self

        class _Q:
            def query(self, body=None):
                class _E:
                    def execute(self_inner):
                        from robot.config import settings
                        return {"calendars": {settings.calendar_id: {"busy": servicio._busy}}}
                return _E()
        return _Q()


def test_b_huecos_profesionales():
    from robot.config import settings

    profs = [
        {"nombre": "Dra. Ruiz", "horarios": {0: (540, 1080), 1: (540, 1080),
                                             2: (540, 1080), 3: (540, 1080),
                                             4: (540, 1080), 5: (540, 840)}},
        {"nombre": "Dr. Santos", "horarios": {0: (600, 1080), 1: (600, 1080),
                                              2: (600, 1080), 3: (600, 1080),
                                              4: (600, 1080)}},
    ]
    original = booking_mod._servicio_calendar
    try:
        booking_mod._servicio_calendar = lambda: _ServicioCalFalso([])
        booking_mod._HUECOS_CACHE.clear()
        huecos = booking_mod.proximos_huecos_por_profesional(profs, AHORA, cantidad=5, dias=3)
    finally:
        booking_mod._servicio_calendar = original
        booking_mod._HUECOS_CACHE.clear()
    caso("(b) Hay huecos con profesional",
         len(huecos) == 5 and all("inicio" in h and "profesional" in h for h in huecos),
         f"{huecos}")
    # El lunes 23 a las 09:00 solo lo puede dar la Dra. Ruiz (Santos entra a las 10).
    nueve = [h for h in huecos if h["inicio"] == LUNES]
    caso("(b) Lunes 09:00 es solo de la Dra. Ruiz",
         nueve and nueve[0]["profesional"] == "Dra. Ruiz", f"{nueve}")
    inicios = [h["inicio"] for h in huecos]
    caso("(b) Ordenados por hora", inicios == sorted(inicios), f"{inicios}")
    caso("(b) Sin profesionales devuelve []",
         booking_mod.proximos_huecos_por_profesional([], AHORA) == [])

    # Con el lunes 09:00-10:00 ocupado, ese hueco desaparece para todos.
    try:
        booking_mod._servicio_calendar = lambda: _ServicioCalFalso(
            [{"start": LUNES, "end": "2026-11-23T10:00:00-07:00"}])
        booking_mod._HUECOS_CACHE.clear()
        huecos2 = booking_mod.proximos_huecos_por_profesional(profs, AHORA, cantidad=5, dias=3)
    finally:
        booking_mod._servicio_calendar = original
        booking_mod._HUECOS_CACHE.clear()
    caso("(b) Hora ocupada bloquea a todos",
         all(h["inicio"] != LUNES for h in huecos2), f"{huecos2}")


# ------------------------------------------------------------------
# (c) Flujo completo con profesional
# ------------------------------------------------------------------

def test_c_flujo_con_profesional():
    limpiar()
    d = DepsV312(
        agente_cola=[RespuestaAgente(
            respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
            quiere_agendar="si", fecha_cita=MARTES, nombre="Jose Ramon",
            motivo="Limpieza")],
        huecos_pro=[{"inicio": MARTES, "profesional": "Dra. Ruiz"},
                    {"inicio": MIERCOLES, "profesional": "Dr. Santos"}],
    )
    r = atender_mensaje(d, TEL, "Jose Ramon", "quiero una cita",
                        con_ritmo=False, ahora=AHORA)
    caso("(c) Se propone cita con botones", len(d.botones) == 1, f"{d.botones}")
    texto_propuesta = d.botones[0][1] if d.botones else ""
    caso("(c) La propuesta nombra a la profesional",
         "con la Dra. Ruiz" in texto_propuesta, texto_propuesta)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(c) La propuesta guarda el profesional",
         propuesta.get("profesional") == "Dra. Ruiz", f"{propuesta}")

    r2 = atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                       fecha_iso=AHORA.isoformat(), con_ritmo=False, ahora=AHORA)
    caso("(c) La cita se crea", len(d.citas) == 1, f"{d.citas}")
    caso("(c) La nota del calendario lleva el profesional",
         d.citas and "Profesional: Dra. Ruiz" in d.citas[0]["nota"],
         f"{d.citas}")
    caso("(c) El espejo lleva el profesional real",
         d.mirror and d.mirror[0]["Profesional"] == "Dra. Ruiz", f"{d.mirror}")
    confirmacion = next(
        (t for _, t in d.textos if "Tu cita quedó para el" in t), "")
    caso("(c) La confirmación dice con quién va",
         "con la Dra. Ruiz" in confirmacion, confirmacion)
    limpiar()


# ------------------------------------------------------------------
# (d) Fallback: sin agenda por profesional
# ------------------------------------------------------------------

def test_d_fallback_sin_profesionales():
    limpiar()
    d = DepsV312(
        agente_cola=[RespuestaAgente(
            respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
            quiere_agendar="si", fecha_cita=MARTES, nombre="Jose Ramon",
            motivo="Limpieza")],
        huecos_pro=[],
    )
    atender_mensaje(d, TEL, "Jose Ramon", "quiero una cita",
                    con_ritmo=False, ahora=AHORA)
    texto_propuesta = d.botones[0][1] if d.botones else ""
    caso("(d) Sin profesional, la propuesta es la de siempre",
         "con la Dra. Ruiz" not in texto_propuesta, texto_propuesta)
    atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                  fecha_iso=AHORA.isoformat(), con_ritmo=False, ahora=AHORA)
    caso("(d) El espejo queda con Equipo de la clínica",
         d.mirror and d.mirror[0]["Profesional"] == "Equipo de la clínica",
         f"{d.mirror}")
    confirmacion = d.textos[-1][1] if d.textos else ""
    caso("(d) La confirmación no inventa profesional",
         "con la Dra. Ruiz" not in confirmacion, confirmacion)
    limpiar()


# ------------------------------------------------------------------
# (e) Urgencia con guía al paciente
# ------------------------------------------------------------------

def test_e_urgencia_con_guia():
    limpiar()
    d = DepsV312()
    r = atender_mensaje(d, TEL, "Jose Ramon", "me duele mucho la muela, es urgente",
                        con_ritmo=False, ahora=AHORA)
    texto = d.textos[0][1] if d.textos else ""
    caso("(e) Urgencia: la IA compone la respuesta",
         len(d.mensajes_al_agente) == 1 and texto == "Claro, te ayudo.", f"{texto}")
    caso("(e) Urgencia: handoff forzado por código",
         r.get("handoff") is True, f"{r}")
    caso("(e) Urgencia: avisa al dueño",
         len(d.alertas_handoff) == 1, f"{d.alertas_handoff}")
    caso("(e) Urgencia: ofrece la cita con botones",
         len(d.botones) == 1, f"{d.botones}")
    limpiar()


# ------------------------------------------------------------------
# (f) Correo de handoff con resumen
# ------------------------------------------------------------------

def test_f_handoff_con_resumen():
    correos = []
    original = mail_mod.enviar_correo
    try:
        mail_mod.enviar_correo = lambda dest, asunto, cuerpo, html=None: correos.append((dest, asunto, cuerpo))
        mail_mod.alerta_handoff("Ana", "5211", "queja", "no me atendieron", "2026-11-22T10:00:00",
                                resumen="Preguntó por limpieza, se enojó por la espera.")
        mail_mod.alerta_handoff("Beto", "5222", "duda", "hola", "2026-11-22T10:00:00")
    finally:
        mail_mod.enviar_correo = original
    caso("(f) Con resumen, el correo lo trae",
         correos and "Preguntó por limpieza" in correos[0][2], f"{correos}")
    caso("(f) Sin resumen, el correo sale igual",
         len(correos) == 2 and "Resumen de la conversación" not in correos[1][2],
         f"{correos}")


# ------------------------------------------------------------------
# (g) Recordatorios
# ------------------------------------------------------------------

def test_g_recordatorios():
    ahora_job = datetime(2026, 11, 22, 20, 0, tzinfo=timezone.utc)  # 13:00 MST domingo
    # Lunes 23 09:00 MST = 20 h después: dentro de la ventana [20h, 28h].
    espejo = [
        {"ID_Cita": "C-1", "Teléfono": TEL, "Servicio": "Limpieza",
         "Profesional": "Dra. Ruiz", "Fecha": "2026-11-23", "Hora_inicio": "09:00",
         "Hora_fin": "10:00", "Estado": "Confirmada", "Origen": "WhatsApp",
         "Recordatorio_enviado": "-", "Confirmado": "Sí",
         "Notas": "Paciente: Jose Ramon", "Creado_por": "Asistente",
         "Última_actualización": "2026-11-22"},
        {"ID_Cita": "C-2", "Teléfono": "521111", "Servicio": "Limpieza",
         "Profesional": "Dra. Ruiz", "Fecha": "2026-11-24", "Hora_inicio": "09:00",
         "Hora_fin": "10:00", "Estado": "Confirmada", "Origen": "WhatsApp",
         "Recordatorio_enviado": "-", "Confirmado": "Sí",
         "Notas": "Paciente: Fuera de ventana", "Creado_por": "Asistente",
         "Última_actualización": "2026-11-22"},
        {"ID_Cita": "C-3", "Teléfono": "522222", "Servicio": "Limpieza",
         "Profesional": "Dra. Ruiz", "Fecha": "2026-11-23", "Hora_inicio": "09:00",
         "Hora_fin": "10:00", "Estado": "Confirmada", "Origen": "WhatsApp",
         "Recordatorio_enviado": "2026-11-21", "Confirmado": "Sí",
         "Notas": "Paciente: Ya enviado", "Creado_por": "Asistente",
         "Última_actualización": "2026-11-22"},
        {"ID_Cita": "C-4", "Teléfono": "523333", "Servicio": "Limpieza",
         "Profesional": "Dra. Ruiz", "Fecha": "2026-11-23", "Hora_inicio": "09:00",
         "Hora_fin": "10:00", "Estado": "Cancelada", "Origen": "WhatsApp",
         "Recordatorio_enviado": "-", "Confirmado": "No",
         "Notas": "Paciente: Cancelada", "Creado_por": "Asistente",
         "Última_actualización": "2026-11-22"},
    ]
    d = DepsV312(espejo=espejo)
    orig_activa = negocio_mod.funcion_activa
    orig_cfg = negocio_mod.configuracion
    try:
        negocio_mod.funcion_activa = lambda nombre: True
        negocio_mod.configuracion = lambda: {
            "plantilla_recordatorio": "recordatorio_cita", "idioma_plantilla": "es_MX"}
        res = rec_mod.enviar_recordatorios_pendientes(d, ahora=ahora_job)
    finally:
        negocio_mod.funcion_activa = orig_activa
        negocio_mod.configuracion = orig_cfg
    caso("(g) Solo se manda la cita en ventana",
         res == {"enviados": 1, "fallidos": 0} and len(d.plantillas) == 1, f"{res} {d.plantillas}")
    if d.plantillas:
        tel, plantilla, idioma, params = d.plantillas[0]
        caso("(g) La plantilla lleva nombre y fecha bonita",
             tel == TEL and plantilla == "recordatorio_cita" and idioma == "es_MX"
             and params[0] == "Jose Ramon" and "lunes 23 de noviembre" in params[1],
             f"{d.plantillas[0]}")
    caso("(g) Se marca Recordatorio_enviado",
         d.actualizaciones and d.actualizaciones[0]["recordatorio_enviado"] == "2026-11-22",
         f"{d.actualizaciones}")

    # Fallo de envío: queda en Diagnóstico, no se marca como enviado.
    d2 = DepsV312(espejo=espejo, plantilla_falla=True)
    try:
        negocio_mod.funcion_activa = lambda nombre: True
        negocio_mod.configuracion = lambda: {
            "plantilla_recordatorio": "recordatorio_cita", "idioma_plantilla": "es_MX"}
        res2 = rec_mod.enviar_recordatorios_pendientes(d2, ahora=ahora_job)
    finally:
        negocio_mod.funcion_activa = orig_activa
        negocio_mod.configuracion = orig_cfg
    caso("(g) Fallo de plantilla: contado y visible en Diagnóstico",
         res2 == {"enviados": 0, "fallidos": 1}
         and d2.diagnosticos and d2.diagnosticos[0]["estado"] == "FALLO",
         f"{res2} {d2.diagnosticos}")
    caso("(g) Fallo: no se marca como enviado",
         d2.actualizaciones == [], f"{d2.actualizaciones}")

    # Interruptor apagado: no manda nada.
    d3 = DepsV312(espejo=espejo)
    try:
        negocio_mod.funcion_activa = lambda nombre: False
        res3 = rec_mod.enviar_recordatorios_pendientes(d3, ahora=ahora_job)
    finally:
        negocio_mod.funcion_activa = orig_activa
    caso("(g) Apagado: no manda nada",
         res3["enviados"] == 0 and d3.plantillas == [], f"{res3}")


# ------------------------------------------------------------------
# (h) Confirmación de asistencia
# ------------------------------------------------------------------

def test_h_confirmacion_asistencia():
    caso("(h) 'confirmo' es confirmación de asistencia",
         _es_confirmacion_asistencia("confirmo") is True)
    caso("(h) 'ahí nos vemos' también",
         _es_confirmacion_asistencia("Ahí nos vemos") is True)
    caso("(h) 'hola' no lo es",
         _es_confirmacion_asistencia("hola buenas") is False)

    espejo = [
        {"ID_Cita": "C-9", "Teléfono": TEL, "Servicio": "Limpieza",
         "Profesional": "Dra. Ruiz", "Fecha": "2026-11-24", "Hora_inicio": "09:00",
         "Hora_fin": "10:00", "Estado": "Confirmada", "Origen": "WhatsApp",
         "Recordatorio_enviado": "2026-11-22", "Confirmado": "Sí",
         "Notas": "Paciente: Jose Ramon", "Creado_por": "Asistente",
         "Última_actualización": "2026-11-22"},
    ]
    limpiar()
    d = DepsV312(espejo=espejo)
    r = atender_mensaje(d, TEL, "Jose Ramon", "confirmo",
                        con_ritmo=False, ahora=AHORA)
    texto = d.textos[-1][1] if d.textos else ""
    caso("(h) Con cita futura, 'confirmo' se registra y responde",
         r.get("confirmacion_asistencia") is True
         and "confirmada tu asistencia" in texto, f"{r} {texto}")
    caso("(h) Queda en las Notas del espejo",
         d.actualizaciones and "confirmó asistencia" in (d.actualizaciones[0]["notas"] or ""),
         f"{d.actualizaciones}")
    caso("(h) No llamó al agente", len(d.mensajes_al_agente) == 0,
         f"{d.mensajes_al_agente}")

    # Sin cita futura: "confirmo" va al agente como cualquier mensaje.
    limpiar()
    d2 = DepsV312(espejo=[])
    atender_mensaje(d2, TEL, "Jose Ramon", "confirmo",
                    con_ritmo=False, ahora=AHORA)
    caso("(h) Sin cita, 'confirmo' va al agente",
         len(d2.mensajes_al_agente) == 1, f"{d2.mensajes_al_agente}")
    limpiar()


# ------------------------------------------------------------------
# (i) Reporte semanal con confirmaciones
# ------------------------------------------------------------------

def test_i_reporte_confirmaciones():
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    espejo = [
        {"Fecha": hoy, "Estado": "Confirmada",
         "Notas": "Paciente: Ana | Paciente confirmó asistencia 2026-11-23"},
        {"Fecha": hoy, "Estado": "Confirmada", "Notas": "Paciente: Beto"},
    ]
    correos = []
    guardados = []
    orig_leer = report_mod.leer_pestana
    orig_texto = report_mod.generar_texto
    orig_correo = report_mod.enviar_correo
    orig_guardar = report_mod.guardar_reporte
    try:
        report_mod.leer_pestana = lambda tab, spreadsheet_id=None: (
            espejo if tab == "Citas" else [])
        report_mod.generar_texto = lambda prompt, json_mode=True: "Resumen."
        report_mod.enviar_correo = lambda dest, asunto, cuerpo, html=None: correos.append((dest, asunto, cuerpo, html))
        report_mod.guardar_reporte = lambda *args: guardados.append(args)
        report_mod.generar_reporte_semanal()
    finally:
        report_mod.leer_pestana = orig_leer
        report_mod.generar_texto = orig_texto
        report_mod.enviar_correo = orig_correo
        report_mod.guardar_reporte = orig_guardar
    cuerpo = correos[0][2] if correos else ""
    html = correos[0][3] if correos and correos[0][3] else ""
    caso("(i) El reporte cuenta 1 confirmación de asistencia",
         "Confirmaciones de asistencia: 1" in cuerpo, cuerpo[:500])
    caso("(i) El HTML también la trae",
         "Confirmaciones de asistencia" in html, html[:300])


# ------------------------------------------------------------------
# (j) Propuestas con profesional sobreviven al reinicio
# ------------------------------------------------------------------

def test_j_cargar_propuestas_profesional():
    limpiar()
    d = DepsV312()
    d.leer_propuestas = lambda: [
        {"telefono": TEL, "nombre": "Jose Ramon", "motivo": "Limpieza",
         "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
         "creado_en": AHORA.isoformat(),
         "extra_json": '{"profesional": "Dra. Ruiz", "cita2": null}'},
        {"telefono": "521111", "nombre": "Ana", "motivo": "Limpieza",
         "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
         "creado_en": AHORA.isoformat(), "extra_json": ""},
    ]
    n = cargar_propuestas(d)
    caso("(j) Se recuperan 2 propuestas", n == 2, f"{n}")
    caso("(j) El profesional viene en extra_json",
         (_CITAS_PENDIENTES.get(TEL) or {}).get("profesional") == "Dra. Ruiz",
         f"{_CITAS_PENDIENTES.get(TEL)}")
    caso("(j) Propuesta vieja sin profesional carga con ''",
         (_CITAS_PENDIENTES.get("521111") or {}).get("profesional") == "",
         f"{_CITAS_PENDIENTES.get('521111')}")
    limpiar()


# ------------------------------------------------------------------
# (k) Retomar la otra cita tras cambiar hora con dos citas
# ------------------------------------------------------------------

def _propuesta_dos_citas():
    return {
        "nombre": "Jose Ramon", "motivo": "Blanqueamiento",
        "fecha_cita": MARTES, "fecha_bonita": "martes 24 de noviembre a las 09:00",
        "creado_en": AHORA.isoformat(), "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "", "numero_paciente": "",
        "cita2": {"motivo": "Blanqueamiento", "fecha_cita": MIERCOLES,
                  "fecha_bonita": "miércoles 25 de noviembre a las 09:00",
                  "nombre_paciente": "", "relacion_paciente": "hermana",
                  "numero_paciente": "", "profesional": ""},
    }


def test_k_retomar():
    # (k1) Cambia la suya: la de la hermana viaja junto con la nueva.
    limpiar()
    _CITAS_PENDIENTES[TEL] = _propuesta_dos_citas()
    d = DepsV312(agente_cola=[RespuestaAgente(
        respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
        quiere_agendar="si", fecha_cita=LUNES, nombre="Jose Ramon",
        motivo="Blanqueamiento")])
    atender_boton(d, TEL, "Jose Ramon", "cambiar_hora", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, "Jose Ramon", "cambiar_mia", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Jose Ramon", "el lunes a las 9",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(k) Cambiar la mía: la propuesta nueva trae la de la hermana",
         (propuesta.get("cita2") or {}).get("fecha_cita") == MIERCOLES,
         f"{propuesta}")
    texto = d.botones[-1][1] if d.botones else ""
    caso("(k) El texto lista las dos y ofrece Confirmar ambas",
         "hermana" in texto and "miércoles 25" in texto
         and [b[1] for b in d.botones[-1][2]][0] == "Confirmar ambas",
         texto)
    atender_boton(d, TEL, "Jose Ramon", "confirmar_cita",
                  fecha_iso=AHORA.isoformat(), con_ritmo=False, ahora=AHORA)
    caso("(k) Confirmar ambas crea las dos citas",
         len(d.citas) == 2
         and {c["fecha_cita"] for c in d.citas} == {LUNES, MIERCOLES},
         f"{d.citas}")
    limpiar()

    # (k2) Cambia la de la hermana: la suya se retoma con etiquetas
    # correctas (la primera es la de ella, la segunda es la del dueño).
    limpiar()
    _CITAS_PENDIENTES[TEL] = _propuesta_dos_citas()
    d = DepsV312(agente_cola=[RespuestaAgente(
        respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
        quiere_agendar="si", fecha_cita=JUEVES, nombre="Jose Ramon",
        motivo="Blanqueamiento", relacion_paciente="hermana")])
    atender_boton(d, TEL, "Jose Ramon", "cambiar_hora", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, "Jose Ramon", "cambiar_de_otra", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Jose Ramon", "el jueves a las 9",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(k) Cambiar la de ella: la retomada es la del dueño (martes)",
         (propuesta.get("cita2") or {}).get("fecha_cita") == MARTES,
         f"{propuesta}")
    texto = d.botones[-1][1] if d.botones else ""
    caso("(k) Etiquetas sin confundir: la de ella + tu cita",
         "La cita de hermana para el jueves 26" in texto
         and "Tu cita para el martes 24" in texto,
         texto)
    limpiar()

    # (k3) Retomar vencida (fecha pasada): no se adjunta.
    limpiar()
    _RETOMAR[TEL] = {"cita": {"motivo": "Blanqueamiento",
                              "fecha_cita": "2026-11-19T09:00:00-07:00",
                              "fecha_bonita": "jueves 19 de noviembre a las 09:00",
                              "nombre_paciente": "", "relacion_paciente": "hermana",
                              "numero_paciente": "", "profesional": ""},
                     "creado_en": AHORA.isoformat()}
    d = DepsV312(agente_cola=[RespuestaAgente(
        respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
        quiere_agendar="si", fecha_cita=MARTES, nombre="Jose Ramon",
        motivo="Blanqueamiento")])
    atender_mensaje(d, TEL, "Jose Ramon", "quiero una cita",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(k) Retomar vencida no se adjunta (propuesta simple)",
         propuesta.get("cita2") is None
         and "Confirmar ambas" not in [b[1] for b in (d.botones[-1][2] if d.botones else [])],
         f"{propuesta} botones={d.botones}")
    caso("(k) La entrada vencida se limpió", TEL not in _RETOMAR)
    limpiar()

    # (k4) Sin propuesta guardada (reinicio): cambiar_mia se comporta
    # como antes y la siguiente propuesta es simple.
    limpiar()
    d = DepsV312(agente_cola=[RespuestaAgente(
        respuesta_texto="¡Con gusto! Te ayudo con tu cita.",
        quiere_agendar="si", fecha_cita=MARTES, nombre="Jose Ramon",
        motivo="Blanqueamiento")])
    r = atender_boton(d, TEL, "Jose Ramon", "cambiar_mia", con_ritmo=False, ahora=AHORA)
    caso("(k) Sin retomar guardado, cambiar_mia responde igual",
         r.get("respondio") is True, f"{r}")
    atender_mensaje(d, TEL, "Jose Ramon", "quiero una cita",
                    con_ritmo=False, ahora=AHORA)
    propuesta = _CITAS_PENDIENTES.get(TEL) or {}
    caso("(k) Sin retomar, la propuesta es simple",
         propuesta.get("cita2") is None, f"{propuesta}")
    limpiar()

    # (k5) Hablar con persona limpia el retomar.
    limpiar()
    _CITAS_PENDIENTES[TEL] = _propuesta_dos_citas()
    d = DepsV312()
    atender_boton(d, TEL, "Jose Ramon", "cambiar_hora", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, "Jose Ramon", "hablar_persona", con_ritmo=False, ahora=AHORA)
    caso("(k) Hablar con persona limpia el retomar", TEL not in _RETOMAR)
    limpiar()

    # (k6) Sin propuesta guardada, el mensaje NO promete retomar lo
    # que no se guardó (honestidad: nunca prometer lo que no pasará).
    limpiar()
    d = DepsV312()
    atender_boton(d, TEL, "Jose Ramon", "cambiar_mia", con_ritmo=False, ahora=AHORA)
    texto = d.textos[-1][1] if d.textos else ""
    caso("(k) Sin retomar guardado, no promete retomarla",
         "retomarla" not in texto and "para la tuya" in texto, texto)
    limpiar()


def main():
    test_a_profesionales()
    test_b_huecos_profesionales()
    test_c_flujo_con_profesional()
    test_d_fallback_sin_profesionales()
    test_e_urgencia_con_guia()
    test_f_handoff_con_resumen()
    test_g_recordatorios()
    test_h_confirmacion_asistencia()
    test_i_reporte_confirmaciones()
    test_j_cargar_propuestas_profesional()
    test_k_retomar()
    print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} pasaron")
    if FALLOS:
        print("FALLARON:", ", ".join(FALLOS))
        sys.exit(1)


if __name__ == "__main__":
    main()
