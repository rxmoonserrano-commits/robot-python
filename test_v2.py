"""Pruebas de la versión 2, SIN internet.

Cubre solo lo nuevo de la v2 (lo de la v1 sigue en test_simulado.py):
(a) visto + "escribiendo..." solo cuando el robot va a contestar,
(b) 3 mensajes rápidos se juntan en UNA sola llamada al agente,
(c) una respuesta larga se parte en 2 mensajes,
(d) un wamid duplicado se ignora,
(e) el botón "Hablar con una persona" hace handoff,
(f) si Gemini falla, el cliente recibe un "dame un momento" y el dueño un correo,
(g) NO existe ningún código que mande recordatorios por WhatsApp,
(h) fuera de horario no se agenda nada imposible,
(i) confirmar la cita con el botón crea la cita y manda la confirmación bonita,
(j) v2.1: con Gmail ausente, un handoff o una falla técnica no rompen
    la respuesta de WhatsApp (el correo es best-effort).

Uso:  python test_v2.py
"""

import pathlib
import re
import time
from datetime import datetime, timedelta, timezone

from robot.agent import RespuestaAgente, preguntar_agente
from robot.agrupar import Agrupador
from robot.logic import atender_boton, atender_mensaje, formatear_cita_bonita
from robot.ritmo import dividir_mensaje

FOTOS = [
    {"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"},
]

CONOCIMIENTO_CON_HORARIO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Servicio 1",
     "respuesta_o_precio": "$500", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]


class DepsV2:
    """Servicios de mentira para la v2: guardan todo en memoria."""

    def __init__(self, bot_activo="SI", ultima_humana="", agente=None,
                 conocimiento=None, alertas_fallan=False, huecos=None):
        # alertas_fallan=True simula Gmail sin configurar: las alertas
        # por correo lanzan el mismo error que mail.CorreoError en real.
        self.alertas_fallan = alertas_fallan
        self.huecos = huecos or []
        self.bot_activo = bot_activo
        self.ultima_humana = ultima_humana
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.conocimiento = conocimiento if conocimiento is not None else [
            {"tipo": "servicio", "pregunta_o_servicio": "Servicio 1",
             "respuesta_o_precio": "$500", "detalle": "Dura 60 minutos"}]
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.fotos_enviadas = []
        self.citas = []
        self.alertas = []
        self.alertas_error = []
        self.marcados = []
        self.botones_enviados = []
        self.llamadas_agente = []

    def leer_control(self):
        return {"bot_activo": self.bot_activo, "ultima_respuesta_humana": self.ultima_humana}

    def leer_conocimiento(self):
        return self.conocimiento

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

    def proximos_huecos_libres(self, conocimiento, ahora):
        return self.huecos

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        self.fotos_enviadas.append((telefono, url))

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        inicio = datetime.fromisoformat(fecha_cita)
        fin = inicio + timedelta(minutes=60)
        cita = {"inicio": inicio.isoformat(), "fin": fin.isoformat()}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        if self.alertas_fallan:
            raise RuntimeError("Falta GMAIL_USER o GMAIL_APP_PASSWORD en el .env.")
        self.alertas.append((nombre, telefono, motivo))

    def marcar_leido_y_escribiendo(self, message_id):
        self.marcados.append(message_id)

    def enviar_botones(self, telefono, texto, botones):
        self.botones_enviados.append((telefono, texto, botones))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        if self.alertas_fallan:
            raise RuntimeError("Falta GMAIL_USER o GMAIL_APP_PASSWORD en el .env.")
        self.alertas_error.append((motivo, telefono))


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def main():
    ahora = datetime.now(timezone.utc)

    # (a) Visto + "escribiendo..." en un mensaje normal, y NO en pausa/apagado.
    d = DepsV2()
    atender_mensaje(d, "6671234567", "Ana", "Hola", message_id="wamid_1", con_ritmo=False)
    caso("(a) Mensaje normal: se marca leído y escribiendo",
         d.marcados == ["wamid_1"], f"marcados={d.marcados}")
    d = DepsV2(ultima_humana=(ahora - timedelta(hours=1)).isoformat())
    atender_mensaje(d, "6671234567", "Ana", "Hola", message_id="wamid_2", con_ritmo=False)
    caso("(a) En pausa humana: NO se marca leído ni escribiendo", d.marcados == [])
    d = DepsV2(bot_activo="NO")
    atender_mensaje(d, "6671234567", "Ana", "Hola", message_id="wamid_3", con_ritmo=False)
    caso("(a) Botón apagado: NO se marca leído ni escribiendo", d.marcados == [])

    # (b) 3 mensajes rápidos se juntan en UNA sola llamada al agente.
    lotes = []

    def procesar(telefono, nombre, textos, wamids):
        lotes.append((telefono, textos))

    agr = Agrupador(procesar, espera_segundos=0.3)
    agr.agregar("6671234567", "Hola", wamid="w1", nombre="Ana")
    agr.agregar("6671234567", "Quiero una cita", wamid="w2")
    agr.agregar("6671234567", "Para el viernes en la mañana", wamid="w3")
    time.sleep(1.0)
    caso("(b) 3 mensajes rápidos = 1 solo lote para el agente",
         len(lotes) == 1 and lotes[0][1] == ["Hola", "Quiero una cita", "Para el viernes en la mañana"],
         f"lotes={lotes}")

    # (d) Un wamid duplicado se ignora (Meta lo reenvió).
    agr2 = Agrupador(procesar, espera_segundos=0.3)
    lotes.clear()
    primero = agr2.agregar("6671234567", "Hola", wamid="w9")
    segundo = agr2.agregar("6671234567", "Hola", wamid="w9")
    time.sleep(0.8)
    caso("(d) Wamid duplicado: se ignora, no se contesta dos veces",
         primero is True and segundo is False and len(lotes) == 1, f"lotes={lotes}")

    # (c) Una respuesta larga se parte en 2 mensajes (nunca un muro de texto).
    texto_largo = (
        "Claro, te cuento todo con calma. Tenemos limpieza dental, blanqueamiento "
        "y ortodoncia, todos con cita previa y con facilidades de pago en efectivo "
        "o con tarjeta, y estamos de lunes a viernes de nueve a seis de la tarde. "
        "También tenemos consultas de valoración sin costo la primera vez, y si "
        "vienes con un familiar, los dos se atienden el mismo día sin problema. "
        "¿Qué día te viene mejor para agendarte?"
    )
    partes = dividir_mensaje(texto_largo)
    caso("(c) Respuesta larga se parte en 2 mensajes cortos",
         len(partes) == 2 and all(len(p) <= 300 for p in partes), f"partes={partes}")
    agente_largo = RespuestaAgente(respuesta_texto=texto_largo)
    d = DepsV2(agente=agente_largo)
    atender_mensaje(d, "6671234567", "Ana", "Cuéntame todo", con_ritmo=False)
    caso("(c) El robot manda los 2 pedazos por WhatsApp",
         len(d.textos_enviados) == 2, f"textos={d.textos_enviados}")

    # (e) Botón "Hablar con una persona" = handoff (correo al dueño).
    d = DepsV2()
    r = atender_boton(d, "6671234567", "Ana", "hablar_persona", con_ritmo=False)
    caso("(e) Botón hablar con persona: handoff",
         r["handoff"] is True and len(d.alertas) == 1 and len(d.clientes) == 1
         and d.clientes[0]["handoff"] == "si", f"r={r}")

    # (i) Confirmar la cita con el botón: crea la cita y la confirmación es bonita.
    agente_agenda = RespuestaAgente(
        respuesta_texto="Perfecto, Ana.",
        nombre="Ana", motivo="Quiere agendar una cita",
        fecha_cita="2026-11-14T10:00:00", quiere_agendar="si")
    d = DepsV2(agente=agente_agenda)
    r = atender_mensaje(d, "6671234567", "Ana", "Soy Ana, quiero cita el sábado a las 10",
                         con_ritmo=False,
                         ahora=datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc))
    caso("(i) Proponer cita: botones, sin crear la cita todavía",
         r.get("cita_propuesta") is True and len(d.citas) == 0
         and len(d.botones_enviados) == 1)
    r2 = atender_boton(d, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("(i) Confirmar: cita creada de 60 min",
         len(d.citas) == 1 and d.citas[0]["fin"] != d.citas[0]["inicio"])
    caso("(i) Confirmación bonita: día, hora y duración",
         any("14 de noviembre" in t and "10:00" in t and "60 minutos" in t
             for _, t in d.textos_enviados), f"textos={d.textos_enviados}")
    d2 = DepsV2(agente=agente_agenda)
    atender_mensaje(d2, "6671234567", "Ana", "Soy Ana, quiero cita", con_ritmo=False,
                    ahora=datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc))
    r3 = atender_boton(d2, "6671234567", "Ana", "cambiar_hora", con_ritmo=False)
    caso("(i) Cambiar hora: no crea cita y pregunta por otro día",
         len(d2.citas) == 0 and any("qué día" in t.lower() for _, t in d2.textos_enviados))

    # (i2) Cita a un mes ("en un mes podría"): el sistema la acepta y
    # propone con botones, sin crear la cita todavía.
    agente_mes = RespuestaAgente(
        respuesta_texto="Perfecto, te agendo el blanqueamiento. "
                        "¿Me das tu nombre completo y a qué número lo registro?",
        nombre="Ana", motivo="Blanqueamiento",
        fecha_cita="2026-12-18T10:00:00", quiere_agendar="si")
    d3 = DepsV2(agente=agente_mes)
    r4 = atender_mensaje(d3, "6671234567", "Ana", "sí, en un mes podría",
                         con_ritmo=False,
                         ahora=datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc))
    caso("(i2) Cita a un mes: propuesta con botones, sin crear la cita",
         r4.get("cita_propuesta") is True and len(d3.citas) == 0
         and len(d3.botones_enviados) == 1
         and "18 de diciembre" in d3.botones_enviados[0][1],
         f"r={r4} botones={d3.botones_enviados}")

    # (i3) Red de seguridad: el cliente dijo "quiero agendar" pero el
    # agente no disparó la propuesta (listó los huecos en texto). El
    # programa propone con el primer hueco libre y pide nombre y número.
    agente_texto = RespuestaAgente(
        respuesta_texto="Claro que sí, tengo espacio mañana sábado a las 10:00 "
                        "o el lunes a las 09:00, ¿cuál te queda mejor?",
        nombre="Ana", motivo="Quiere agendar")
    d4 = DepsV2(agente=agente_texto,
                huecos=["2026-11-14T10:00:00-07:00", "2026-11-16T09:00:00-07:00"])
    r5 = atender_mensaje(d4, "6679999999", "Ana", "sí, quiero agendar una",
                         con_ritmo=False,
                         ahora=datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc))
    caso("(i3) Red de seguridad: 'quiero agendar' sin propuesta → botones + nombre",
         r5.get("cita_propuesta") is True and len(d4.citas) == 0
         and len(d4.botones_enviados) == 1
         and "nombre completo" in d4.botones_enviados[0][1],
         f"r={r5} botones={d4.botones_enviados}")

    # (f) Si Gemini falla: el cliente recibe "dame un momento" y el dueño un correo.
    agente_falla = RespuestaAgente.segura(
        "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
        falla_tecnica=True)
    d = DepsV2(agente=agente_falla)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola", con_ritmo=False)
    caso("(f) Gemini falla: el cliente SÍ recibe un mensaje (no silencio)",
         r["respondio"] is True and any("momento" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    caso("(f) Gemini falla: el dueño recibe la alerta de error",
         len(d.alertas_error) == 1, f"alertas_error={d.alertas_error}")

    # (f2) El agente real, con Gemini roto, devuelve la respuesta segura con falla.
    import robot.agent as agent_mod
    real = agent_mod.generar_texto
    try:
        agent_mod.generar_texto = lambda prompt: (_ for _ in ()).throw(RuntimeError("Gemini caído"))
        resp = preguntar_agente("Hola", [], [], [])
        caso("(f) Agente real con Gemini caído: handoff con falla_tecnica",
             resp.necesita_handoff == "si" and resp.falla_tecnica is True)
    finally:
        agent_mod.generar_texto = real

    # (h) Fuera de horario (v2.6): la IA contesta siempre, con contexto
    # de cerrado. No se agenda nada imposible, y ya no hay frase grabada.
    # Domingo 2026-11-15 a las 20:00 (hora de Mazatlán): el negocio está cerrado.
    domingo_noche = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)  # = domingo 20:00 MST
    d = DepsV2(conocimiento=CONOCIMIENTO_CON_HORARIO)
    r = atender_mensaje(d, "6671234567", "Ana", "Quiero una cita ahorita",
                         con_ritmo=False, ahora=domingo_noche)
    caso("(h) Fuera de horario: llama al agente con contexto de cerrado",
         len(d.llamadas_agente) == 1 and "CERRADO" in d.llamadas_agente[0]
         and "lunes 16 de noviembre" in d.llamadas_agente[0],
         f"llamadas={d.llamadas_agente}")
    caso("(h) Fuera de horario: no crea la cita",
         len(d.citas) == 0, f"citas={d.citas}")
    caso("(h) Fuera de horario: el cliente recibe la respuesta del agente",
         any("Qué día te viene mejor" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    # En horario (lunes 10:00 Mazatlán = 17:00 UTC) sí atiende normal.
    lunes_manana = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)
    d = DepsV2(conocimiento=CONOCIMIENTO_CON_HORARIO)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola", con_ritmo=False, ahora=lunes_manana)
    caso("(h) En horario: atiende normal",
         r.get("fuera_de_horario") is not True and len(d.llamadas_agente) == 1)

    # (j) v2.1 — Gmail ausente: el correo falla, pero el cliente NO se
    # queda sin respuesta. Regresión del bug real: con GMAIL_USER /
    # GMAIL_APP_PASSWORD vacíos, alerta_handoff / alerta_error lanzaban
    # CorreoError y rompían atender_mensaje (o el fallback de _procesar_lote).
    agente_handoff = RespuestaAgente(
        respuesta_texto="Te paso con una persona.",
        nombre="Ana", motivo="Quiere hablar con una persona",
        necesita_handoff="si", motivo_handoff="El cliente pidió hablar con una persona")
    d = DepsV2(agente=agente_handoff, alertas_fallan=True)
    try:
        r = atender_mensaje(d, "6671234567", "Ana", "Quiero hablar con una persona",
                             con_ritmo=False)
        sin_error_handoff = True
    except Exception as exc:  # noqa: BLE001
        r = {}
        sin_error_handoff = False
        print(f"  (j) error inesperado: {exc}")
    caso("(j) Handoff no-técnico sin Gmail: no lanza excepción",
         sin_error_handoff and r.get("handoff") is True)
    caso("(j) Handoff no-técnico sin Gmail: el cliente queda registrado como handoff",
         len(d.clientes) == 1 and d.clientes[0]["handoff"] == "si",
         f"clientes={d.clientes}")

    d = DepsV2(agente=agente_falla, alertas_fallan=True)
    try:
        r = atender_mensaje(d, "6671234567", "Ana", "Hola", con_ritmo=False)
        sin_error_falla = True
    except Exception as exc:  # noqa: BLE001
        r = {}
        sin_error_falla = False
        print(f"  (j) error inesperado: {exc}")
    caso("(j) Falla técnica sin Gmail: no lanza excepción",
         sin_error_falla and r.get("respondio") is True)
    caso("(j) Falla técnica sin Gmail: el cliente recibe UN 'dame un momento'",
         [t for _, t in d.textos_enviados].count(
             "Dame un momento, por favor. Estoy revisando tu mensaje y "
             "te atiendo enseguida.") == 1,
         f"textos={d.textos_enviados}")

    d = DepsV2(alertas_fallan=True)
    try:
        r = atender_boton(d, "6671234567", "Ana", "hablar_persona", con_ritmo=False)
        sin_error_boton = True
    except Exception as exc:  # noqa: BLE001
        r = {}
        sin_error_boton = False
        print(f"  (j) error inesperado: {exc}")
    caso("(j) Botón hablar con persona sin Gmail: no lanza excepción",
         sin_error_boton and r.get("handoff") is True)
    caso("(j) Botón hablar con persona sin Gmail: el cliente sí recibe su texto",
         any("persona del negocio" in t for _, t in d.textos_enviados)
         and len(d.clientes) == 1 and d.clientes[0]["handoff"] == "si",
         f"textos={d.textos_enviados} clientes={d.clientes}")

    # Formato bonito de la cita.
    caso("Formato: sábado 14 de noviembre a las 10:00",
         formatear_cita_bonita("2026-11-14T10:00:00") == "sábado 14 de noviembre a las 10:00",
         formatear_cita_bonita("2026-11-14T10:00:00"))

    # (g) NO existe código que mande recordatorios por WhatsApp.
    # Se revisa solo el código de producción (app.py + robot/), no las
    # pruebas: los comentarios pueden decir "no hay recordatorios", pero
    # lo que importa es que no haya ninguna función ni trabajo que los mande.
    raiz = pathlib.Path(__file__).parent
    prod = [raiz / "app.py", raiz / "instalar.py"] + list((raiz / "robot").glob("*.py"))
    textos_py = "\n".join(f.read_text(errors="ignore") for f in prod if f.exists())
    caso("(g) No hay función que mande recordatorios por WhatsApp",
         "enviar_recordatorio" not in textos_py
         and not re.search(r"def \w*recordatorio", textos_py, re.IGNORECASE),
         "se encontró código de recordatorios")
    # (v3.3) Ahora son DOS trabajos programados, los dos por correo y
    # nunca por WhatsApp: el reporte semanal y el resumen de la mañana.
    caso("(g) Los únicos trabajos programados son el reporte semanal y el resumen de la mañana (por correo)",
         textos_py.count("add_job") == 2
         and 'id="reporte-semanal"' in textos_py
         and 'id="resumen-manana"' in textos_py)

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
