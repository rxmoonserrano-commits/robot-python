"""Pruebas simuladas del robot, SIN internet.

No llama a WhatsApp, ni a Gemini, ni a Google: todo es falso.
Sirve para comprobar que la lógica no se rompe antes de gastar
tiempo en claves reales.

Uso:  python test_simulado.py
Salida: PASS o FAIL por cada caso, y un resumen al final.
"""

from datetime import datetime, timedelta, timezone

from robot.agent import RespuestaAgente
from robot.logic import Dependencias, atender_mensaje, contar_semana, foto_es_oficial, puede_responder

FOTOS = [
    {"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"},
    {"descripcion": "Foto del servicio", "url": "https://ejemplo.com/foto-servicio.jpg"},
]
# URL que el agente inventó: NO está en la lista blanca.
FOTO_FALSA = "https://inventada.com/foto-mala.jpg"


class DepsFalsas(Dependencias):
    """Servicios de mentira: guardan todo en memoria."""

    def __init__(self, bot_activo="SI", ultima_humana="", agente=None):
        self.bot_activo = bot_activo
        self.ultima_humana = ultima_humana
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?",
            nombre="Ana",
            motivo="Quiere agendar una cita",
            fecha_cita="2026-11-14T10:00:00",
            quiere_agendar="si",
        )
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.fotos_enviadas = []
        self.citas = []
        self.alertas = []
        # --- Nuevos en la v2 (se registran, no se mandan de verdad) ---
        self.marcados = []        # wamids con visto + "escribiendo..."
        self.botones_enviados = []  # (telefono, texto, botones)
        self.alertas_error = []

    def leer_control(self):
        return {"bot_activo": self.bot_activo, "ultima_respuesta_humana": self.ultima_humana}

    def leer_conocimiento(self):
        return [{"tipo": "servicio", "pregunta_o_servicio": "Servicio 1",
                 "respuesta_o_precio": "$500", "detalle": "Dura 60 minutos"}]

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
        return self.agente

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        self.fotos_enviadas.append((telefono, url))

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        inicio = datetime.fromisoformat(fecha_cita)
        fin = inicio + timedelta(minutes=60)  # igual que booking.py: 60 min, no inicio=fin
        cita = {"inicio": inicio.isoformat(), "fin": fin.isoformat()}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas.append((nombre, telefono, motivo))

    # --- Nuevos en la v2 ---
    def marcar_leido_y_escribiendo(self, message_id):
        self.marcados.append(message_id)

    def enviar_botones(self, telefono, texto, botones):
        self.botones_enviados.append((telefono, texto, botones))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        self.alertas_error.append((motivo, telefono))


# --- Los casos ---

RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def main():
    ahora = datetime.now(timezone.utc)

    # 1. Botón apagado: el robot NO responde, pero el mensaje queda registrado.
    d = DepsFalsas(bot_activo="NO")
    r = atender_mensaje(d, "6671234567", "Ana", "Hola, quiero una cita", con_ritmo=False)
    caso("1. Botón apagado: no responde", r["respondio"] is False and not d.textos_enviados)
    caso("1. Botón apagado: el mensaje queda guardado",
         any(c["motivo"] == "boton apagado" for c in d.conversaciones))

    # 2. Humano atendió hace 1 hora: el robot se calla (pausa de 2 h).
    hace_1h = (ahora - timedelta(hours=1)).isoformat()
    d = DepsFalsas(ultima_humana=hace_1h)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola de nuevo", con_ritmo=False)
    caso("2. Pausa humana < 2 h: no responde", r["respondio"] is False and not d.textos_enviados)
    caso("2. Pausa humana < 2 h: motivo correcto",
         any("humano activo" in c["motivo"] for c in d.conversaciones))

    # 3. Humano atendió hace 3 horas: la pausa ya pasó, el robot retoma.
    hace_3h = (ahora - timedelta(hours=3)).isoformat()
    d = DepsFalsas(ultima_humana=hace_3h)
    r = atender_mensaje(d, "6671234567", "Ana", "Hola, quiero una cita", con_ritmo=False)
    caso("3. Pausa humana > 2 h: vuelve a responder",
         r["respondio"] is True and (len(d.textos_enviados) + len(d.botones_enviados)) == 1)

    # 4. Foto inventada: la lista blanca la bloquea, no se manda.
    caso("4. Foto oficial sí pasa la lista blanca",
         foto_es_oficial("https://ejemplo.com/foto-local.jpg", FOTOS))
    caso("4. Foto inventada NO pasa la lista blanca",
         not foto_es_oficial(FOTO_FALSA, FOTOS))
    agente_foto_mala = RespuestaAgente(
        respuesta_texto="Te mando la foto.", foto_oficial_url_or_null=FOTO_FALSA)
    d = DepsFalsas(agente=agente_foto_mala)
    atender_mensaje(d, "6671234567", "Ana", "¿Me mandas una foto?", con_ritmo=False)
    caso("4. Foto inventada: no se envía por WhatsApp", d.fotos_enviadas == [])

    # 5. Foto oficial: sí se manda, antes del texto.
    agente_foto_buena = RespuestaAgente(
        respuesta_texto="Claro, aquí está.",
        foto_oficial_url_or_null="https://ejemplo.com/foto-local.jpg")
    d = DepsFalsas(agente=agente_foto_buena)
    atender_mensaje(d, "6671234567", "Ana", "¿Me mandas una foto del local?", con_ritmo=False)
    caso("5. Foto oficial: sí se envía",
         d.fotos_enviadas == [("6671234567", "https://ejemplo.com/foto-local.jpg")])

    # 6. Flujo normal de agendar (v2): propone con botones, NO crea la cita
    # todavía. Al tocar Confirmar, se crea la cita de 60 min y se registra.
    from robot.logic import atender_boton
    d = DepsFalsas()
    r = atender_mensaje(d, "6671234567", "Ana", "Soy Ana, quiero una cita el 14 a las 10",
                         con_ritmo=False,
                         ahora=datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc))
    caso("6. Agendar: propone con botones (no crea la cita todavía)",
         r.get("cita_propuesta") is True and len(d.citas) == 0
         and len(d.botones_enviados) == 1, f"r={r}")
    caso("6. Agendar: los botones son Confirmar / Cambiar hora / Hablar con persona",
         [b[0] for b in d.botones_enviados[0][2]] == ["confirmar_cita", "cambiar_hora", "hablar_persona"])
    r2 = atender_boton(d, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("6. Agendar: al confirmar, cita creada con duración de 60 min",
         len(d.citas) == 1 and d.citas[0]["fin"] != d.citas[0]["inicio"],
         f"cita={d.citas}")
    caso("6. Agendar: la confirmación trae día, hora y duración",
         any("14 de noviembre" in t and "60 minutos" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    caso("6. Agendar: cliente registrado en Clientes como agendado",
         any(c["estatus"] == "agendado" for c in d.clientes))
    caso("6. Agendar: conversación registrada en Conversaciones",
         any(c["quien_hablo"] == "robot" for c in d.conversaciones))

    # 7. Handoff: correo al dueño, cliente marcado... y (v3.3.1) el
    # cliente TAMBIÉN recibe el texto. Antes quedaba en silencio.
    agente_handoff = RespuestaAgente(
        respuesta_texto="Te paso con una persona.",
        necesita_handoff="si", motivo_handoff="El cliente pide hablar con una persona",
        nombre="Ana", motivo="Quiere hablar con una persona")
    d = DepsFalsas(agente=agente_handoff)
    r = atender_mensaje(d, "6671234567", "Ana", "Quiero hablar con una persona", con_ritmo=False)
    caso("7. Handoff: el cliente recibe el texto del handoff",
         r["handoff"] is True and len(d.textos_enviados) == 1
         and "persona" in d.textos_enviados[0][1])
    caso("7. Handoff: alerta mandada al dueño", len(d.alertas) == 1)
    caso("7. Handoff: cliente marcado con handoff=si",
         len(d.clientes) == 1 and d.clientes[0]["handoff"] == "si")

    # 8. Contar la semana: los números salen de las hojas.
    hoy = ahora
    conv = [
        {"fecha": hoy.isoformat(), "telefono": "1", "quien_hablo": "robot",
         "mensaje": "hola", "robot_respondio": "si", "motivo": "Quiere agendar"},
        {"fecha": hoy.isoformat(), "telefono": "1", "quien_hablo": "cliente",
         "mensaje": "hola", "robot_respondio": "no", "motivo": "humano activo hace menos de 2 horas"},
        {"fecha": (hoy - timedelta(days=30)).isoformat(), "telefono": "1",
         "quien_hablo": "robot", "mensaje": "viejo", "robot_respondio": "si", "motivo": ""},
    ]
    cli = [
        {"fecha": hoy.isoformat(), "nombre": "Ana", "telefono": "1",
         "motivo": "Quiere agendar", "fecha_cita": "2026-11-14", "origen": "whatsapp",
         "estatus": "agendado", "handoff": "no"},
        {"fecha": hoy.isoformat(), "nombre": "Luis", "telefono": "2",
         "motivo": "Queja", "fecha_cita": "", "origen": "whatsapp",
         "estatus": "en conversacion", "handoff": "si"},
    ]
    conteo = contar_semana(conv, cli, hoy - timedelta(days=7), hoy + timedelta(days=1))
    caso("8. Reporte: cuenta solo la última semana (no el mensaje viejo)",
         conteo["mensajes_atendidos"] == 1, f"conteo={conteo}")
    caso("8. Reporte: clientes, citas y handoffs correctos",
         conteo["clientes_calificados"] == 2 and conteo["citas_agendadas"] == 1
         and conteo["handoffs"] == 1 and conteo["sin_respuesta_por_humano"] == 1,
         f"conteo={conteo}")

    # 9. Regla pura de puede_responder.
    caso("9. puede_responder: SI y sin humano = sí", puede_responder("SI", "")[0] is True)
    caso("9. puede_responder: NO = no", puede_responder("NO", "")[0] is False)
    caso("9. puede_responder: humano hace 30 min = no",
         puede_responder("SI", (ahora - timedelta(minutes=30)).isoformat())[0] is False)

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
