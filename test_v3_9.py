"""Pruebas de la versión 3.9, SIN internet.

Estructura Sereno adoptada:
(a) duracion_servicio: lee la duración por servicio de Conocimiento
    (columna Duración_min), sin acentos y con contención.
(b) Confirmar cita: el mensaje dice la duración REAL del servicio
    y la cita queda en el espejo (pestaña Citas) como Confirmada.
(c) Calendario falla con la hora libre → la solicitud queda
    PENDIENTE: se le dice al cliente, se avisa al dueño y el espejo
    queda Pendiente (Sereno decisión 1: nunca inventar una cita).
(d) Hora ocupada (ValueError de booking) → el mensaje de siempre,
    sin espejo ni alerta de pendiente (regresión).
(e) Cancelar: el espejo se marca Cancelada.
(f) Reporte semanal: cuenta canceladas/no-show desde el espejo y
    manda la versión HTML además del texto.
(g) enviar_correo con html: multipart con parte HTML.
(h) Guion: el protocolo de urgencias de la hoja entra al guion;
    sin protocolo, el guion sale igual que siempre.

Uso:  python test_v3_9.py
"""

import smtplib
from datetime import datetime, timedelta, timezone

import robot.agent as agent_mod
import robot.mail as mail_mod
import robot.report as report_mod
import robot.sheets as sheets_mod
from robot.config import settings
from robot.logic import (
    Dependencias,
    _CITAS_PENDIENTES,
    _atender_cambio_cancelacion,
    _confirmar_cita_propuesta,
    _fila_espejo,
    atender_mensaje,
)
from robot.agent import RespuestaAgente

RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


# ------------------------------------------------------------------
# (a) duracion_servicio
# ------------------------------------------------------------------

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos",
     "Duración_min": "60"},
    {"tipo": "servicio", "pregunta_o_servicio": "Extracción simple",
     "respuesta_o_precio": "$700", "detalle": "Con anestesia",
     "Duración_min": "45"},
    {"tipo": "servicio", "pregunta_o_servicio": "Servicio sin duración",
     "respuesta_o_precio": "$100", "detalle": "-",
     "Duración_min": "abc"},
    {"tipo": "faq", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "Pregunta frecuente", "detalle": "-",
     "Duración_min": "999"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
]


def _con_conocimiento(monkeypatch):
    monkeypatch.setattr(sheets_mod, "leer_conocimiento", lambda: CONOCIMIENTO)


def test_duracion(monkeypatch):
    _con_conocimiento(monkeypatch)
    caso("(a) Duración: coincidencia exacta",
         sheets_mod.duracion_servicio("Limpieza dental") == 60)
    caso("(a) Duración: sin acentos ni mayúsculas",
         sheets_mod.duracion_servicio("EXTRACCION simple") == 45)
    caso("(a) Duración: contención (motivo corto)",
         sheets_mod.duracion_servicio("limpieza") == 60)
    caso("(a) Duración: sin coincidencia → None",
         sheets_mod.duracion_servicio("Blanqueamiento") is None)
    caso("(a) Duración: valor inválido → None",
         sheets_mod.duracion_servicio("Servicio sin duración") is None)
    caso("(a) Duración: fila no-servicio ignorada",
         sheets_mod.duracion_servicio("Limpieza dental") != 999)


# ------------------------------------------------------------------
# Fakes para logic
# ------------------------------------------------------------------

class DepsV39(Dependencias):
    """Servicios de mentira: guardan todo en memoria."""

    def __init__(self, duracion=45, crear_falla=None):
        self.duracion = duracion
        self.crear_falla = crear_falla
        self.textos = []
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.espejo = []
        self.espejo_updates = []
        self.alertas_pendiente = []
        self.cliente = {}

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono,
                                    "quien_hablo": quien, "mensaje": mensaje,
                                    "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"nombre": nombre, "telefono": telefono, "motivo": motivo,
                              "fecha_cita": fecha_cita, "estatus": estatus})

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        if self.crear_falla is not None:
            raise self.crear_falla
        cita = {"inicio": fecha_cita}
        self.citas.append(cita)
        return cita

    def duracion_servicio(self, motivo):
        return self.duracion

    def registrar_cita_espejo(self, fila):
        self.espejo.append(fila)

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado):
        self.espejo_updates.append((telefono, fecha_cita, estado))

    def alerta_cita_pendiente(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_pendiente.append((nombre, telefono, motivo, fecha_bonita))

    def leer_cliente(self, telefono):
        return self.cliente or None

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


def _propuesta(telefono, motivo="Extracción simple"):
    return {
        "nombre": "Ana",
        "telefono_registro": "6671234567",
        "motivo": motivo,
        "fecha_cita": "2026-11-25T10:00:00-07:00",
        "fecha_bonita": "miércoles 25 de noviembre a las 10:00",
    }


# ------------------------------------------------------------------
# (b) Confirmar: duración real + espejo Confirmada
# ------------------------------------------------------------------

def test_confirmar_con_duracion():
    tel = "6679990001"
    _CITAS_PENDIENTES[tel] = _propuesta(tel)
    d = DepsV39(duracion=45)
    r = _confirmar_cita_propuesta(d, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(b) Confirmar: respuesta ok", r.get("respondio") is True, f"r={r}")
    caso("(b) Confirmar: dice la duración real (45, no 60)",
         any("Dura 45 minutos." in t for _, t in d.textos), f"textos={d.textos}")
    caso("(b) Confirmar: espejo registrado como Confirmada",
         len(d.espejo) == 1 and d.espejo[0]["Estado"] == "Confirmada", f"espejo={d.espejo}")
    fila = d.espejo[0] if d.espejo else {}
    caso("(b) Espejo: hora fin = inicio + duración",
         fila.get("Hora_inicio") == "10:00" and fila.get("Hora_fin") == "10:45", f"fila={fila}")
    caso("(b) Espejo: fecha y servicio correctos",
         fila.get("Fecha") == "2026-11-25" and fila.get("Servicio") == "Extracción simple",
         f"fila={fila}")


def test_confirmar_sin_duracion_usa_default():
    tel = "6679990002"
    _CITAS_PENDIENTES[tel] = _propuesta(tel)
    d = DepsV39(duracion=None)
    _confirmar_cita_propuesta(d, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(b) Sin duración en hoja: usa el default de 60",
         any("Dura 60 minutos." in t for _, t in d.textos), f"textos={d.textos}")


# ------------------------------------------------------------------
# (c) Calendario falla con hora libre → pendiente
# ------------------------------------------------------------------

def test_cita_pendiente():
    tel = "6679990003"
    _CITAS_PENDIENTES[tel] = _propuesta(tel)
    d = DepsV39(crear_falla=RuntimeError("Calendar no contestó"))
    r = _confirmar_cita_propuesta(d, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(c) Pendiente: motivo del resultado",
         r.get("motivo") == "cita pendiente", f"r={r}")
    caso("(c) Pendiente: se le dice al cliente con honestidad",
         any("pendiente" in t.lower() for _, t in d.textos), f"textos={d.textos}")
    caso("(c) Pendiente: NO se le dice que ya se ocupó",
         not any("ya se ocupó" in t for _, t in d.textos), f"textos={d.textos}")
    caso("(c) Pendiente: se avisa al dueño",
         len(d.alertas_pendiente) == 1, f"alertas={d.alertas_pendiente}")
    caso("(c) Pendiente: espejo queda Pendiente (no Confirmada)",
         len(d.espejo) == 1 and d.espejo[0]["Estado"] == "Pendiente", f"espejo={d.espejo}")
    caso("(c) Pendiente: no se creó cita ni cliente agendado",
         not d.citas and not [c for c in d.clientes if c["estatus"] == "agendado"],
         f"citas={d.citas} clientes={d.clientes}")


# ------------------------------------------------------------------
# (d) Hora ocupada → mensaje de siempre (regresión)
# ------------------------------------------------------------------

def test_hora_ocupada():
    tel = "6679990004"
    _CITAS_PENDIENTES[tel] = _propuesta(tel)
    d = DepsV39(crear_falla=ValueError("La hora ya está ocupada"))
    r = _confirmar_cita_propuesta(d, tel, "Ana", "2026-11-22T16:00:00+00:00", con_ritmo=False)
    _CITAS_PENDIENTES.pop(tel, None)
    caso("(d) Ocupada: motivo del resultado", r.get("motivo") == "hora ocupada", f"r={r}")
    caso("(d) Ocupada: mensaje de siempre",
         any("ya se ocupó" in t for _, t in d.textos), f"textos={d.textos}")
    caso("(d) Ocupada: sin espejo ni alerta de pendiente",
         not d.espejo and not d.alertas_pendiente, f"espejo={d.espejo}")


# ------------------------------------------------------------------
# (e) Cancelar → espejo Cancelada
# ------------------------------------------------------------------

def test_cancelar_actualiza_espejo():
    tel = "6679990005"
    _CITAS_PENDIENTES.pop(tel, None)
    d = DepsV39()
    d.cliente = {"estatus": "agendado", "fecha_cita": "2026-11-25T10:00:00-07:00"}
    r = _atender_cambio_cancelacion(d, tel, "Ana", "2026-11-22T16:00:00+00:00",
                                    "cancelar", con_ritmo=False)
    caso("(e) Cancelar: espejo marcado Cancelada",
         d.espejo_updates == [(tel, "2026-11-25T10:00:00-07:00", "Cancelada")],
         f"updates={d.espejo_updates}")
    caso("(e) Cancelar: respuesta ok", r.get("cita_cancelada") is True, f"r={r}")


# ------------------------------------------------------------------
# (f) Reporte semanal: conteo desde espejo + HTML
# ------------------------------------------------------------------

def test_reporte(monkeypatch):
    hoy = datetime.now(timezone.utc)
    dia = hoy.strftime("%Y-%m-%d")
    ayer = (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    viejo = (hoy - timedelta(days=30)).strftime("%Y-%m-%d")

    conversaciones = [{"fecha": hoy.isoformat(), "robot_respondio": "si"}]
    clientes = [{
        "fecha": hoy.isoformat(), "nombre": "Ana", "telefono": "6671",
        "motivo": "Limpieza", "fecha_cita": f"{dia}T10:00:00-07:00",
        "estatus": "agendado", "handoff": "no",
    }]
    citas_espejo = [
        {"Fecha": dia, "Estado": "Cancelada"},
        {"Fecha": ayer, "Estado": "No-show"},
        {"Fecha": viejo, "Estado": "Cancelada"},  # fuera de ventana: no cuenta
        {"Fecha": dia, "Estado": "Confirmada"},
    ]

    def leer_fake(pestana, spreadsheet_id=None):
        return {"Conversaciones": conversaciones, "Clientes": clientes,
                "Citas": citas_espejo}.get(pestana, [])

    capturado = {}

    def enviar_fake(dest, asunto, cuerpo, html=None):
        capturado["dest"] = dest
        capturado["asunto"] = asunto
        capturado["cuerpo"] = cuerpo
        capturado["html"] = html

    monkeypatch.setattr(report_mod, "leer_pestana", leer_fake)
    monkeypatch.setattr(report_mod, "contar_semana", lambda c, cl, d, h: {
        "mensajes_atendidos": 10, "clientes_calificados": 1, "citas_agendadas": 1,
        "handoffs": 0, "sin_respuesta_por_humano": 0, "motivos_top": [("Limpieza", 1)],
    })
    monkeypatch.setattr(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
    monkeypatch.setattr(report_mod, "enviar_correo", enviar_fake)
    monkeypatch.setattr(report_mod, "guardar_reporte", lambda *a, **k: None)
    monkeypatch.setattr(report_mod, "funcion_activa", lambda n: True)

    report_mod.generar_reporte_semanal()
    cuerpo = capturado.get("cuerpo", "")
    html = capturado.get("html", "")
    caso("(f) Reporte: el texto cuenta canceladas y no-show",
         "Canceladas: 1 · No-show: 1" in cuerpo, f"cuerpo={cuerpo[:300]}")
    caso("(f) Reporte: llega versión HTML",
         isinstance(html, str) and "CITAS CONFIRMADAS" in html and "TU SEMANA EN NÚMEROS" in html,
         f"html={str(html)[:200]}")
    caso("(f) Reporte: HTML con KPIs reales",
         "10" in html and "Resumen de prueba." in html, f"html={str(html)[:200]}")


# ------------------------------------------------------------------
# (g) enviar_correo con html → multipart
# ------------------------------------------------------------------

class _FakeSMTP:
    capturado = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        _FakeSMTP.capturado.append(msg)


def test_mail_html(monkeypatch):
    _FakeSMTP.capturado = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(settings, "gmail_user", "robot@ejemplo.com")
    monkeypatch.setattr(settings, "gmail_app_password", "xxxx xxxx xxxx xxxx")
    mail_mod.enviar_correo("dueno@ejemplo.com", "Asunto", "Texto plano", html="<p>Bonito</p>")
    caso("(g) Correo: se mandó uno", len(_FakeSMTP.capturado) == 1)
    msg = _FakeSMTP.capturado[0] if _FakeSMTP.capturado else None
    caso("(g) Correo: es multipart con HTML",
         msg is not None and msg.get_content_type() == "multipart/alternative"
         and any(p.get_content_type() == "text/html" for p in msg.get_payload()),
         f"tipo={msg.get_content_type() if msg else None}")


# ------------------------------------------------------------------
# (h) Guion con protocolo de urgencias
# ------------------------------------------------------------------

def test_guion_protocolo(monkeypatch):
    monkeypatch.setattr(agent_mod, "protocolo_urgencias",
                        lambda: "Orientar a atención inmediata. No dar indicaciones.")
    caso("(h) Guion: incluye el protocolo de la hoja",
         "Protocolo de urgencias" in agent_mod.guion())
    monkeypatch.setattr(agent_mod, "protocolo_urgencias", lambda: "")
    caso("(h) Guion: sin protocolo, sale igual que siempre",
         "Protocolo de urgencias" not in agent_mod.guion())


# ------------------------------------------------------------------
# _fila_espejo (unidad)
# ------------------------------------------------------------------

def test_fila_espejo():
    fila = _fila_espejo(
        {"motivo": "Limpieza", "fecha_cita": "2026-11-25T10:00:00-07:00"},
        "6671234567", "Ana", 45, "Confirmada", "2026-11-22T16:00:00+00:00")
    caso("(i) Espejo: horas calculadas",
         fila["Hora_inicio"] == "10:00" and fila["Hora_fin"] == "10:45", f"fila={fila}")
    caso("(i) Espejo: fecha del día",
         fila["Fecha"] == "2026-11-25", f"fila={fila}")
    fila2 = _fila_espejo({"motivo": "X", "fecha_cita": "fecha-rara"},
                         "6671234567", "", 60, "Pendiente", "2026-11-22")
    caso("(i) Espejo: fecha rara no rompe",
         fila2["Hora_inicio"] == "" and fila2["Estado"] == "Pendiente", f"fila={fila2}")


# ------------------------------------------------------------------
# (j) Doble "dame un momento" (v3.9.1): si el vigilante ya mandó el
# aviso (lote > 90 s), la falla técnica NO manda el mismo texto otra
# vez. El registro en la hoja y los avisos quedan igual.
# ------------------------------------------------------------------

class DepsFalla:
    """Deps mínimo para atender_mensaje con un agente que falla."""

    def __init__(self):
        self.textos = []
        self.conversaciones = []
        self.diagnosticos = []
        self.alertas_error = []
        self.clientes = []
        self.escribiendo = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return None

    def leer_conocimiento(self):
        return [{"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
                 "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"}]

    def leer_fotos(self):
        return []

    def leer_historial(self, telefono):
        return []

    def leer_propuestas(self):
        return []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        return RespuestaAgente(
            respuesta_texto="Dame un momento, por favor. Estoy revisando tu mensaje y "
                            "te atiendo enseguida.",
            necesita_handoff="si",
            motivo_handoff="Gemini no contestó: 503",
            falla_tecnica=True,
        )

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def enviar_botones(self, telefono, texto, botones):
        pass

    def marcar_leido_y_escribiendo(self, message_id):
        self.escribiendo.append(message_id)

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"quien": quien, "mensaje": mensaje, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"telefono": telefono, "handoff": handoff})

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append((componente, estado))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        self.alertas_error.append((motivo, telefono))

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass


_AHORA_J = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


def test_doble_aviso_suprimido():
    # Con la bandera del vigilante en True: NO se manda el texto otra vez.
    d = DepsFalla()
    r = atender_mensaje(d, "5216694608263", "Jose", "me da miedo",
                        con_ritmo=False, ahora=_AHORA_J,
                        aviso_lote_enviado={"si": True})
    caso("(j) Doble aviso: con vigilante, no se manda el texto dos veces",
         d.textos == [] and r.get("handoff") is True,
         f"textos={d.textos} r={r}")
    caso("(j) Doble aviso: el registro y los avisos quedan igual",
         [c for c in d.conversaciones if c["quien"] == "robot"]
         and [c for c in d.conversaciones if c["quien"] == "robot"][0]["motivo"] == "falla tecnica"
         and len(d.alertas_error) == 1
         and len(d.diagnosticos) == 1,
         f"conversaciones={d.conversaciones} alertas={d.alertas_error}")

    # Sin bandera (lote rápido): el texto sí se manda, como siempre.
    d2 = DepsFalla()
    r2 = atender_mensaje(d2, "5216694608263", "Jose", "me da miedo",
                         con_ritmo=False, ahora=_AHORA_J)
    caso("(j) Doble aviso: sin vigilante, el texto sí se manda",
         len(d2.textos) == 1 and r2.get("handoff") is True,
         f"textos={d2.textos} r={r2}")


def test_burbuja_sin_refresco():
    """(k) Ritmo natural (v3.9.2): la burbuja se prende UNA vez por
    lote (paso 3) y ya no hay hilo que la refresque sin fin."""
    import robot.logic as logic_mod

    caso("(k) Burbuja: ya no existe el refresco infinito",
         not hasattr(logic_mod, "_refrescar_escribiendo"))

    d = DepsFalla()
    atender_mensaje(d, "5216694608263", "Jose", "me da miedo",
                    con_ritmo=False, ahora=_AHORA_J)
    caso("(k) Burbuja: se prende una sola vez por lote",
         len(d.escribiendo) == 1, f"escribiendo={d.escribiendo}")


def main():
    class MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, nombre, valor):
            self._undo.append((obj, nombre, getattr(obj, nombre)))
            setattr(obj, nombre, valor)

        def undo(self):
            for obj, nombre, valor in reversed(self._undo):
                setattr(obj, nombre, valor)

    mp = MP()
    try:
        test_duracion(mp)
        test_confirmar_con_duracion()
        test_confirmar_sin_duracion_usa_default()
        test_cita_pendiente()
        test_hora_ocupada()
        test_cancelar_actualiza_espejo()
        test_reporte(mp)
        test_mail_html(mp)
        test_guion_protocolo(mp)
        test_fila_espejo()
        test_doble_aviso_suprimido()
        test_burbuja_sin_refresco()
    finally:
        mp.undo()
        _CITAS_PENDIENTES.clear()

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
