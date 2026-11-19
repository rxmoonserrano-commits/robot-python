"""Pruebas de inteligencia de la IA — batería por categorías (v3.4.9).

Sin internet ni clave de API: el agente es falso, pero TODO lo demás
es el código real del robot (botones, agenda, handoff, documento de
info, calidez). Es la batería que Jose pidió para verificar que la
inteligencia maneja cada situación con calidad.

Categorías:
  A. Botones        — propuesta, confirmar, cambiar hora, hablar con persona
  B. Agenda         — fechas, huecos, cambios, cancelaciones, registro
  C. Handoff        — urgencia, enojo, pausa humana, botón apagado
  D. Documento      — Conocimiento, fotos oficiales, horarios
  E. Calidez        — saludo, regreso, "lo voy a pensar", partes, humano

Corre en cualquier lado (sin .env ni red):

    python test_inteligencia.py
"""

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from robot import logic as logic_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_boton, atender_mensaje

TEL = "6671234567"
AHORA = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)  # mié 09:00 Mazatlán
CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]
FECHA_OK = "2026-11-20T10:00:00"  # viernes 10:00, dentro de horario


class DepsI:
    """Servicios de mentira: guardan todo en memoria para poder revisar."""

    def __init__(self, agente=None, agente_cola=None, conocimiento=None,
                 fotos=None, cliente=None, huecos=None, hora_libre=True,
                 bot_activo="SI", ultima_humana="", historial_extra=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.agente_cola = list(agente_cola or [])
        self.conocimiento = conocimiento if conocimiento is not None else CONOCIMIENTO
        self.fotos = fotos if fotos is not None else FOTOS
        self.cliente = cliente
        self.huecos = huecos or []
        self.hora_libre_resultado = hora_libre
        self.bot_activo = bot_activo
        self.ultima_humana = ultima_humana
        self.historial_extra = historial_extra or []
        self.conversaciones = []
        self.clientes = []
        self.textos = []
        self.fotos_env = []
        self.botones = []
        self.citas = []
        self.citas_notas = []
        self.citas_canceladas = []
        self.clientes_cancelados = []
        self.alertas_handoff = []
        self.alertas_cita = []
        self.alertas_lead = []
        self.alertas_error = []
        self.marcados = []
        self.llamadas = []          # (mensaje_agente, conocimiento)
        self.diagnosticos = []

    # --- Sheets ---
    def leer_control(self):
        return {"bot_activo": self.bot_activo, "ultima_respuesta_humana": self.ultima_humana}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return self.cliente

    def leer_conocimiento(self):
        return self.conocimiento

    def leer_fotos(self):
        return self.fotos

    def leer_historial(self, telefono):
        return [c for c in self.conversaciones if c["telefono"] == telefono] + self.historial_extra

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
                                    "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"nombre": nombre, "telefono": telefono, "motivo": motivo,
                              "fecha_cita": fecha_cita, "estatus": estatus, "handoff": handoff})

    def cancelar_cita_cliente(self, telefono):
        self.clientes_cancelados.append(telefono)

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias=""):
        pass

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append((componente, estado, detalle))

    # --- Agente ---
    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.llamadas.append((mensaje, conocimiento))
        if self.agente_cola:
            return self.agente_cola.pop(0)
        return self.agente

    # --- WhatsApp ---
    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        self.fotos_env.append((telefono, url))

    def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, texto, botones))

    def marcar_leido_y_escribiendo(self, message_id):
        self.marcados.append(message_id)

    # --- Calendar ---
    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        inicio = datetime.fromisoformat(fecha_cita)
        fin = inicio + timedelta(minutes=60)
        cita = {"inicio": inicio.isoformat(), "fin": fin.isoformat(), "nombre": nombre}
        self.citas.append(cita)
        self.citas_notas.append(nota)
        return cita

    def cancelar_cita(self, telefono, fecha_cita):
        self.citas_canceladas.append((telefono, fecha_cita))
        return True

    def proximos_huecos_libres(self, conocimiento, ahora):
        return self.huecos

    def hora_libre(self, fecha_iso):
        return self.hora_libre_resultado

    # --- Correo ---
    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas_handoff.append((nombre, telefono, motivo))

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        self.alertas_cita.append((nombre, telefono, motivo))

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas_lead.append((nombre, telefono, motivo))

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        self.alertas_error.append((motivo, telefono))


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def agente_propone(fecha=FECHA_OK, texto="Claro, te agendo la limpieza.", nombre=""):
    return RespuestaAgente(respuesta_texto=texto, nombre=nombre, motivo="Limpieza",
                           fecha_cita=fecha, quiere_agendar="si")


def main():
    print("=" * 60)
    print("A. BOTONES")
    print("=" * 60)

    # A1. La propuesta sale con los 3 botones.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("A1 Propuesta con botones Confirmar / Cambiar hora / Hablar con persona",
         len(d.botones) == 1 and [b[0] for b in d.botones[0][2]] == ["confirmar_cita", "cambiar_hora", "hablar_persona"],
         f"botones={d.botones}")

    # A2. Botón Confirmar → cita creada + confirmación bonita.
    r = atender_boton(d, TEL, "Ana", "confirmar_cita", con_ritmo=False, ahora=AHORA)
    caso("A2 Botón Confirmar crea la cita y confirma bonito",
         len(d.citas) == 1 and any("Tu cita quedó" in t for _, t in d.textos),
         f"citas={d.citas} textos={d.textos}")

    # A3. Botón Cambiar hora → propuesta borrada + pregunta por otro día.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, "Ana", "cambiar_hora", con_ritmo=False, ahora=AHORA)
    caso("A3 Botón Cambiar hora borra la propuesta y pregunta por otro día",
         TEL not in logic_mod._CITAS_PENDIENTES
         and any("Qué día y hora" in t for _, t in d.textos),
         f"textos={d.textos}")

    # A4. Botón Hablar con persona → handoff (texto + correo al dueño).
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, "Ana", "hablar_persona", con_ritmo=False, ahora=AHORA)
    caso("A4 Botón Hablar con persona: texto al cliente + alerta al dueño",
         len(d.alertas_handoff) == 1 and len(d.textos) >= 1,
         f"alertas={d.alertas_handoff} textos={d.textos}")

    # A5. Confirmar por texto "sí" → cita creada.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "sí", con_ritmo=False, ahora=AHORA)
    caso("A5 'sí' por texto confirma la cita",
         len(d.citas) == 1 and any("Tu cita quedó" in t for _, t in d.textos),
         f"citas={d.citas}")

    # A6. Emoji 👍 con propuesta → confirma.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "👍", con_ritmo=False, ahora=AHORA)
    caso("A6 '👍' con propuesta confirma la cita", len(d.citas) == 1, f"citas={d.citas}")

    # A7. La propuesta pide nombre completo y número de registro.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("A7 La propuesta pide nombre completo y número de registro",
         d.botones and "nombre completo" in d.botones[0][1] and "número registrarlo" in d.botones[0][1],
         f"botones={d.botones}")

    # A8. Sin doble pregunta: "¿Te agendo?" del agente se quita.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone(texto="Perfecto. ¿Te agendo para el viernes a las 10?"))
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("A8 Sin doble pregunta de confirmación",
         d.botones and "¿Te agendo" not in d.botones[0][1] and "¿Confirmo tu cita" in d.botones[0][1],
         f"botones={d.botones}")

    print("=" * 60)
    print("B. AGENDA")
    print("=" * 60)

    # B1. La cita dura 60 minutos.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "sí", con_ritmo=False, ahora=AHORA)
    if d.citas:
        ini = datetime.fromisoformat(d.citas[0]["inicio"])
        fin = datetime.fromisoformat(d.citas[0]["fin"])
        minutos = (fin - ini).total_seconds() / 60
    else:
        minutos = 0
    caso("B1 La cita confirmada dura 60 minutos", minutos == 60, f"minutos={minutos}")

    # B2. Hora fuera de horario (domingo) → se corrige al siguiente
    # día hábil DESPUÉS de lo pedido (lunes), no a mañana.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone(fecha="2026-11-22T10:00:00"))  # domingo
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    fecha_guardada = logic_mod._CITAS_PENDIENTES.get(TEL, {}).get("fecha_cita", "")
    caso("B2 Fecha en domingo (cerrado) se corrige a lunes 09:00",
         fecha_guardada.startswith("2026-11-23T09:00"), f"fecha={fecha_guardada}")

    # B3. Hora ocupada → se usa el primer hueco libre real.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone(), huecos=["2026-11-21T09:00:00"], hora_libre=False)
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    fecha_guardada = logic_mod._CITAS_PENDIENTES.get(TEL, {}).get("fecha_cita", "")
    caso("B3 Hora ocupada: la propuesta usa el primer hueco libre",
         fecha_guardada == "2026-11-21T09:00:00", f"fecha={fecha_guardada}")

    # B4. Cambiar con fecha específica → propuesta nueva, sin preguntar otra vez.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente_cola=[agente_propone(),
                           agente_propone(fecha="2026-11-21T09:00:00",
                                          texto="Claro, te la muevo al sábado a las 9.")])
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    n_llamadas = len(d.llamadas)
    r = atender_mensaje(d, TEL, "Ana", "mejor el sábado a las 9", con_ritmo=False, ahora=AHORA)
    caso("B4 'Mejor el sábado a las 9': va al agente y propone la nueva hora",
         len(d.llamadas) == n_llamadas + 1 and r.get("cita_propuesta") is True
         and logic_mod._CITAS_PENDIENTES.get(TEL, {}).get("fecha_cita") == "2026-11-21T09:00:00",
         f"r={r} llamadas={len(d.llamadas)}")

    # B5. "no" a la propuesta → borra y pregunta por otro día.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    n_textos = len(d.textos)
    atender_mensaje(d, TEL, "Ana", "no", con_ritmo=False, ahora=AHORA)
    caso("B5 'no' con propuesta: borra y pregunta por otro día",
         TEL not in logic_mod._CITAS_PENDIENTES
         and any("Qué día y hora" in t for _, t in d.textos[n_textos:]),
         f"textos={d.textos}")

    # B6. Cancelar cita creada → evento borrado + confirmación.
    logic_mod._CITAS_PENDIENTES.clear()
    cliente_agendado = {"nombre": "Ana", "fecha_cita": "2026-11-20T10:00:00",
                        "estatus": "agendado", "handoff": "no"}
    d = DepsI(cliente=cliente_agendado)
    atender_mensaje(d, TEL, "Ana", "quiero cancelar mi cita", con_ritmo=False, ahora=AHORA)
    caso("B6 Cancelar cita creada: borra el evento y lo confirma",
         len(d.citas_canceladas) == 1 and any("quedó cancelada" in t for _, t in d.textos),
         f"canceladas={d.citas_canceladas} textos={d.textos}")

    # B7. Nombre dado después de la propuesta → confirmación con nombre.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente_cola=[agente_propone(),
                           RespuestaAgente(respuesta_texto="Perfecto, gracias.",
                                           nombre="Juan Pérez García", motivo="Limpieza")])
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "me llamo Juan Pérez García", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "sí", con_ritmo=False, ahora=AHORA)
    caso("B7 La confirmación sale con el nombre completo del cliente",
         any("Juan Pérez García" in t for _, t in d.textos) and len(d.citas) == 1,
         f"textos={d.textos}")

    # B8. Número de registro → la cita queda registrada a ese número.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente_cola=[agente_propone(),
                           RespuestaAgente(respuesta_texto="Perfecto.", nombre="Juan Pérez",
                                           motivo="Limpieza")])
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "regístralo al 6679876543", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "sí", con_ritmo=False, ahora=AHORA)
    caso("B8 La cita lleva el número de registro (nota + mensaje)",
         any("6679876543" in n for n in d.citas_notas)
         and any("Quedó registrada al" in t for _, t in d.textos),
         f"notas={d.citas_notas} textos={d.textos}")

    # B9. Alerta de cita confirmada al dueño.
    caso("B9 Al confirmar, el dueño recibe la alerta de cita",
         len(d.alertas_cita) == 1, f"alertas={d.alertas_cita}")

    print("=" * 60)
    print("C. HANDOFF")
    print("=" * 60)

    # C1. Urgencia → handoff inmediato, sin llamar al agente.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI()
    r = atender_mensaje(d, TEL, "Ana", "me duele mucho la muela", con_ritmo=False, ahora=AHORA)
    caso("C1 Urgencia: handoff inmediato sin agente",
         r.get("handoff") is True and len(d.llamadas) == 0
         and len(d.alertas_handoff) == 1
         and any("Te paso con una persona" in t for _, t in d.textos),
         f"r={r} llamadas={len(d.llamadas)} textos={d.textos}")

    # C2. Agente pide handoff (cliente enojado) → texto + alerta + registro.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(
        respuesta_texto="Entiendo tu molestia, te paso con una persona del negocio.",
        necesita_handoff="si", motivo_handoff="Cliente enojado", nombre="Ana",
        motivo="Queja"))
    r = atender_mensaje(d, TEL, "Ana", "esto es una porquería, quiero hablar con alguien",
                        con_ritmo=False, ahora=AHORA)
    caso("C2 Handoff del agente: texto, alerta y cliente marcado",
         r.get("handoff") is True and len(d.alertas_handoff) == 1
         and any(c["handoff"] == "si" for c in d.clientes)
         and any("te paso con una persona" in t for _, t in d.textos),
         f"r={r} clientes={d.clientes}")

    # C3. Pausa humana (<2 h) → el robot no responde ni llama al agente.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(ultima_humana=(AHORA - timedelta(minutes=30)).isoformat())
    r = atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    caso("C3 Humano activo hace <2 h: el robot se queda callado",
         r.get("respondio") is False and len(d.llamadas) == 0 and len(d.textos) == 0,
         f"r={r}")

    # C4. Botón apagado → no responde.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(bot_activo="NO")
    r = atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    caso("C4 Botón apagado: el robot no responde",
         r.get("respondio") is False and len(d.llamadas) == 0, f"r={r}")

    # C5. Falla técnica → "dame un momento" + alerta de error + Diagnóstico.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente.segura("Dame un momento, por favor.", falla_tecnica=True))
    r = atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    caso("C5 Falla técnica: 'dame un momento', alerta y registro",
         r.get("falla_tecnica") is True and len(d.alertas_error) == 1
         and len(d.diagnosticos) >= 1
         and any("Dame un momento" in t for _, t in d.textos),
         f"r={r} diag={d.diagnosticos}")

    print("=" * 60)
    print("D. DOCUMENTO DE INFO (Conocimiento)")
    print("=" * 60)

    # D1. Foto no oficial → NO se envía.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(
        respuesta_texto="Claro, aquí está.", nombre="Ana", motivo="Foto",
        foto_oficial_url_or_null="https://malo.com/foto.jpg"))
    atender_mensaje(d, TEL, "Ana", "mándame una foto", con_ritmo=False, ahora=AHORA)
    caso("D1 Foto fuera de la lista blanca: no se envía",
         len(d.fotos_env) == 0, f"fotos={d.fotos_env}")

    # D2. Foto oficial → sí se envía.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(
        respuesta_texto="Claro, aquí está.", nombre="Ana", motivo="Foto",
        foto_oficial_url_or_null="https://ejemplo.com/foto-local.jpg"))
    atender_mensaje(d, TEL, "Ana", "mándame una foto", con_ritmo=False, ahora=AHORA)
    caso("D2 Foto oficial: sí se envía",
         len(d.fotos_env) == 1, f"fotos={d.fotos_env}")

    # D3. El Conocimiento llega al agente (precios y horarios de la hoja).
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(respuesta_texto="La limpieza cuesta $600."))
    atender_mensaje(d, TEL, "Ana", "¿cuánto cuesta la limpieza?", con_ritmo=False, ahora=AHORA)
    conocimiento_recibido = d.llamadas[0][1] if d.llamadas else []
    caso("D3 El agente recibe el Conocimiento de la hoja",
         any("$600" in str(f.get("respuesta_o_precio", "")) for f in conocimiento_recibido)
         and d.llamadas and "[Contexto:" in d.llamadas[0][0],
         f"conocimiento={conocimiento_recibido}")

    # D4. Sin filas de horario en la hoja → la propuesta no se bloquea.
    logic_mod._CITAS_PENDIENTES.clear()
    sin_horario = [{"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
                    "respuesta_o_precio": "$600", "detalle": ""}]
    d = DepsI(agente=agente_propone(), conocimiento=sin_horario)
    r = atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    caso("D4 Sin horarios en la hoja: la propuesta sale igual",
         r.get("cita_propuesta") is True, f"r={r}")

    print("=" * 60)
    print("E. CALIDEZ Y ENTENDIMIENTO")
    print("=" * 60)

    # E1. Saludo solo → no ofrece cita (el revisor quita la oferta).
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(
        respuesta_texto="¡Buenas noches! ¿Te agendo tu limpieza para mañana a las 9:00?",
        nombre="Ana", motivo="Saludo"))
    atender_mensaje(d, TEL, "Ana", "buenas noches", con_ritmo=False, ahora=AHORA)
    enviados = " ".join(t for _, t in d.textos)
    caso("E1 Saludo solo: no ofrece cita, saluda y pregunta",
         "¿Te agendo" not in enviados and "¿En qué te puedo ayudar?" in enviados,
         f"enviados={enviados!r}")

    # E2. Cliente que vuelve → el contexto recuerda de qué hablaban.
    logic_mod._CITAS_PENDIENTES.clear()
    cliente_con_memoria = {"nombre": "Ana", "resumen_conversacion": "Hablaban de la limpieza",
                           "intereses": "la limpieza", "proxima_accion": "", "notas": ""}
    historial_previo = [
        {"fecha": (AHORA - timedelta(days=2)).isoformat(), "telefono": TEL,
         "quien_hablo": "cliente", "mensaje": "¿cuánto cuesta la limpieza?", "robot_respondio": "si", "motivo": ""},
        {"fecha": (AHORA - timedelta(days=2)).isoformat(), "telefono": TEL,
         "quien_hablo": "robot", "mensaje": "La limpieza cuesta $600.", "robot_respondio": "si", "motivo": ""},
    ]
    d = DepsI(agente=RespuestaAgente(respuesta_texto="¡Hola! Qué bueno que volviste."),
              cliente=cliente_con_memoria, historial_extra=historial_previo)
    atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    mensaje_agente = d.llamadas[0][0] if d.llamadas else ""
    caso("E2 Cliente que vuelve: el contexto recuerda la conversación",
         "Hablaban de la limpieza" in mensaje_agente or "ya ha hablado contigo antes" in mensaje_agente,
         f"mensaje={mensaje_agente[:200]}")

    # E3. "Lo voy a pensar" con propuesta → la propuesta sigue viva.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente_cola=[agente_propone(),
                           RespuestaAgente(
                               respuesta_texto="Claro, piénsalo con calma. Te aparto el lugar hasta mañana sin compromiso.",
                               nombre="Ana", motivo="Lo va a pensar")])
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    n_botones = len(d.botones)
    atender_mensaje(d, TEL, "Ana", "lo voy a pensar", con_ritmo=False, ahora=AHORA)
    caso("E3 'Lo voy a pensar': la propuesta sigue viva, sin botones nuevos",
         TEL in logic_mod._CITAS_PENDIENTES and len(d.botones) == n_botones,
         f"propuestas={logic_mod._CITAS_PENDIENTES} botones={len(d.botones)}")

    # E4. "ok" con propuesta → confirma.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "ok", con_ritmo=False, ahora=AHORA)
    caso("E4 'ok' con propuesta confirma la cita", len(d.citas) == 1, f"citas={d.citas}")

    # E5. Emoji solo sin propuesta → respuesta cálida sin llamar a la IA.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI()
    atender_mensaje(d, TEL, "Ana", "❤️", con_ritmo=False, ahora=AHORA)
    caso("E5 Emoji solo: respuesta cálida sin agente",
         len(d.llamadas) == 0 and any("¿En qué te ayudo hoy?" in t for _, t in d.textos),
         f"llamadas={len(d.llamadas)} textos={d.textos}")

    # E6. Varias preguntas en un mensaje → una sola llamada con todo el texto.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(respuesta_texto="Te contesto todo."))
    atender_mensaje(d, TEL, "Ana", "¿cuánto cuesta?\n¿dónde están?\n¿qué horario?",
                    con_ritmo=False, ahora=AHORA)
    caso("E6 Tres preguntas juntas: una sola llamada con el texto completo",
         len(d.llamadas) == 1 and "¿cuánto cuesta?" in d.llamadas[0][0]
         and "¿qué horario?" in d.llamadas[0][0],
         f"llamadas={len(d.llamadas)}")

    # E7. "Sí gracias" tras un aviso de falla NO confirma la cita.
    logic_mod._CITAS_PENDIENTES.clear()
    historial_fallo = [
        {"fecha": AHORA.isoformat(), "telefono": TEL, "quien_hablo": "robot",
         "mensaje": "Dame un momento, por favor. Estoy revisando tu mensaje y te atiendo enseguida.",
         "robot_respondio": "si", "motivo": "falla tecnica"},
    ]
    d = DepsI(agente=agente_propone(), historial_extra=historial_fallo)
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, TEL, "Ana", "sí gracias", con_ritmo=False, ahora=AHORA)
    caso("E7 'Sí gracias' tras una falla: no confirma, atiende normal",
         len(d.citas) == 0 and len(d.llamadas) >= 2,
         f"citas={d.citas} llamadas={len(d.llamadas)}")

    # E8. Pregunta con propuesta pendiente → texto sin botones nuevos.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente_cola=[agente_propone(),
                           RespuestaAgente(
                               respuesta_texto="La limpieza cuesta $600, dura 60 minutos y no duele.",
                               nombre="Ana", motivo="Limpieza", fecha_cita=FECHA_OK,
                               quiere_agendar="si")])
    atender_mensaje(d, TEL, "Ana", "quiero una cita", con_ritmo=False, ahora=AHORA)
    n_botones = len(d.botones)
    atender_mensaje(d, TEL, "Ana", "¿y cuánto cuesta?", con_ritmo=False, ahora=AHORA)
    caso("E8 Pregunta con propuesta pendiente: texto sin botones duplicados",
         len(d.botones) == n_botones and TEL in logic_mod._CITAS_PENDIENTES
         and any("$600" in t for _, t in d.textos),
         f"botones={len(d.botones)} textos={d.textos}")

    # E9. Partes → varios mensajes en orden.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=RespuestaAgente(
        respuesta_texto="Hola. ¿En qué te ayudo?", nombre="Ana", motivo="Saludo",
        partes=["Hola, buenas noches.", "¿En qué te ayudo hoy?"]))
    atender_mensaje(d, TEL, "Ana", "hola", con_ritmo=False, ahora=AHORA)
    enviados = [t for _, t in d.textos]
    caso("E9 Partes: llegan como mensajes separados y en orden",
         enviados == ["Hola, buenas noches.", "¿En qué te ayudo hoy?"],
         f"enviados={enviados}")

    # E10. "Hola, quiero agendar" no es saludo: la oferta no se quita.
    logic_mod._CITAS_PENDIENTES.clear()
    d = DepsI(agente=agente_propone())
    r = atender_mensaje(d, TEL, "Ana", "hola quiero agendar", con_ritmo=False, ahora=AHORA)
    caso("E10 'Hola, quiero agendar': propone con botones",
         r.get("cita_propuesta") is True and len(d.botones) == 1,
         f"r={r} botones={d.botones}")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print("=" * 60)
    print(f"{pasaron}/{len(RESULTADOS)} pruebas de inteligencia pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
