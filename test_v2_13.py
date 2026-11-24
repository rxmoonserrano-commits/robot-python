"""Pruebas de la versión 2.13 (motor nuevo), SIN internet.

Cubre solo lo nuevo de la v2.13:
(a) robot/estado.py: el estado del cliente se calcula por código
    (etapa saludo / pregunto / oferta_pendiente / agendado / nuevo).
(b) robot/revision.py: el revisor corrige antes de mandar (R1 no
    repetir la oferta, R2 no ofrecer en un saludo, R3 "ya cerramos").
(c) robot/gemini.py: la llamada va con frenos (temperatura 0.3,
    JSON obligatorio en la API, tope de 600 tokens); el audio sigue
    en texto plano.
(d) robot/logic.py: el estado viaja en el mensaje al agente y el
    revisor corre en vivo (con registro en Diagnóstico).

Uso:  python test_v2_13.py
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import robot.agent as agent_mod
import robot.gemini as gemini_mod
import robot.logic as logic_mod
from robot.config import settings
from robot.estado import estado_cliente
from robot.logic import atender_mensaje, formatear_cita_bonita, _parse_fecha_iso
from robot.revision import revisar_respuesta

CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]
FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]

PROPUESTA = {
    "nombre": "Jose Ramon", "motivo": "Quiere una limpieza",
    "fecha_cita": "2026-11-16T09:00:00", "fecha_bonita": "lunes 16 de noviembre a las 09:00",
    "creado_en": "2026-11-13T04:00:00+00:00",
}


def fila(quien, mensaje, motivo=""):
    return {"fecha": "2026-11-13T04:00:00+00:00", "telefono": "5216694608263",
            "quien_hablo": quien, "mensaje": mensaje, "robot_respondio": "si",
            "motivo": motivo}


class DepsV213:
    """Servicios de mentira."""

    def __init__(self, historial=None, agente_json=None, cliente=None):
        self.historial = historial or []
        self.agente_json = agente_json
        self.cliente = cliente
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.botones_enviados = []
        self.diagnostico = []
        self.mensajes_al_agente = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_robot_activo(self, telefono):
        return "SI"

    def leer_cliente(self, telefono):
        return self.cliente

    def cancelar_cita(self, telefono, fecha_cita):
        return False

    def cancelar_cita_cliente(self, telefono):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def leer_propuestas(self):
        return []

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
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita, "origen": origen,
                              "estatus": estatus, "handoff": handoff})

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_al_agente.append(mensaje)
        return agent_mod.preguntar_agente(mensaje, conocimiento, fotos, historial)

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        return {"inicio": fecha_cita}

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen="", hilo=""):
        pass

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


class _RespFalsa:
    def __init__(self, texto):
        self.status_code = 200
        self._texto = texto

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._texto}]}}]}


def main():
    # ---- (a) Estado del cliente ----
    e = estado_cliente([], None, None)
    caso("(a) Sin historial: etapa nuevo", e["etapa"] == "nuevo" and not e["ya_ofrecio_cita"])
    e = estado_cliente([fila("cliente", "buenas noches")], None, None, "Jose Ramon")
    caso("(a) Solo un saludo: etapa saludo",
         e["etapa"] == "saludo" and e["ultimo_mensaje_cliente"] == "buenas noches")
    e = estado_cliente([fila("cliente", "hola"), fila("robot", "Hola, ¿en qué te ayudo?"),
                        fila("cliente", "buenas noches")], None, None)
    caso("(a) Saludo aunque ya haya hablado antes: etapa saludo",
         e["etapa"] == "saludo")
    e = estado_cliente([fila("cliente", "¿cuánto cuesta la limpieza?")], None, None)
    caso("(a) Pregunta de precio: etapa pregunto", e["etapa"] == "pregunto")
    # (v3.4.9) Un saludo con intención no es solo un saludo.
    e = estado_cliente([fila("cliente", "hola quiero agendar")], None, None)
    caso("(a) 'hola quiero agendar': etapa pregunto, no saludo",
         e["etapa"] == "pregunto", f"etapa={e['etapa']}")
    e = estado_cliente([fila("cliente", "buenas, ¿cuánto cuesta?")], None, None)
    caso("(a) 'buenas, ¿cuánto cuesta?': etapa pregunto",
         e["etapa"] == "pregunto", f"etapa={e['etapa']}")
    e = estado_cliente([fila("cliente", "buenas noches"),
                        fila("robot", "¿Te la agendo para mañana a las 9:00?")],
                       PROPUESTA, None)
    caso("(a) Con propuesta: etapa oferta_pendiente",
         e["etapa"] == "oferta_pendiente" and e["ya_ofrecio_cita"]
         and e["oferta_fecha_bonita"] == "lunes 16 de noviembre a las 09:00"
         and e["ultimo_mensaje_robot"].startswith("¿Te la agendo"))
    e = estado_cliente([fila("cliente", "hola")], None,
                       {"nombre": "Jose Ramon", "fecha_cita": "2026-11-13T09:00:00-07:00",
                        "estatus": "agendado"})
    caso("(a) Con cita creada: etapa agendado y tiene_cita",
         e["etapa"] == "agendado" and e["tiene_cita"] and e["nombre"] == "Jose Ramon")

    # ---- (b) Revisor ----
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600, dura 60 minutos. ¿Te la agendo para mañana a las 9:00?",
        {"etapa": "oferta_pendiente", "ya_ofrecio_cita": True})
    caso("(b) R1: repite la oferta y se quita, el precio queda",
         "¿Te la agendo" not in texto and "$600" in texto and v == ["R1"],
         f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "¿Te la agendo para mañana a las 9:00 o el sábado a las 10:00?",
        {"etapa": "oferta_pendiente", "ya_ofrecio_cita": True})
    caso("(b) R1: si la respuesta ERA solo la oferta, recuerda los horarios",
         "Los horarios que te dejé arriba" in texto and v == ["R1"],
         f"salió: {texto!r}")
    texto, v = revisar_respuesta(
        "¡Buenas noches! ¿Te agendo tu limpieza para mañana a las 9:00?",
        {"etapa": "saludo", "ya_ofrecio_cita": False}, "Jose Ramon")
    caso("(b) R2: en un saludo no ofrece cita, saluda y pregunta",
         "¿Te agendo" not in texto and "¿En qué te puedo ayudar?" in texto and v == ["R2"],
         f"salió: {texto!r}")
    texto, v = revisar_respuesta(
        "Con gusto te atiendo, ahorita ya cerramos pero abrimos mañana.",
        {"etapa": "saludo"})
    caso("(b) R3: 'ya cerramos' se cambia por 'el negocio cerró, yo te atiendo'",
         "el negocio ya cerró por hoy, pero yo te atiendo igual" in texto.lower()
         and "ya cerramos" not in texto.lower() and v == ["R3"],
         f"salió: {texto!r}")
    texto, v = revisar_respuesta(
        "Claro, piénsalo con calma. Te aparto el lugar hasta mañana sin compromiso, ¿te parece?",
        {"etapa": "oferta_pendiente", "ya_ofrecio_cita": True})
    caso("(b) Apartar el lugar NO es una oferta nueva: no se quita",
         "Te aparto el lugar hasta mañana sin compromiso" in texto and v == [],
         f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "La agenda de mañana está llena, pero el sábado a las 10:00 sí hay lugar.",
        {"etapa": "oferta_pendiente", "ya_ofrecio_cita": True})
    caso("(b) Hablar de la agenda no es ofrecer: no se quita",
         texto.startswith("La agenda de mañana está llena") and v == [],
         f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600, dura 60 minutos y no duele.",
        {"etapa": "pregunto", "ya_ofrecio_cita": False})
    caso("(b) Respuesta limpia: no se toca",
         texto.startswith("La limpieza cuesta $600") and v == [],
         f"salió: {texto!r} {v}")
    # (v3.4.9) "¿Te reservo...?" también es una oferta: se quita.
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600. ¿Te reservo para mañana a las 9:00?",
        {"etapa": "oferta_pendiente", "ya_ofrecio_cita": True})
    caso("(b) R1: '¿Te reservo...?' también se quita",
         "¿Te reservo" not in texto and "$600" in texto and v == ["R1"],
         f"salió: {texto!r} {v}")

    # ---- (c) Frenos en la llamada a Gemini ----
    clave_vieja, modelo_viejo = settings.gemini_api_key, gemini_mod._ULTIMO_MODELO_OK
    try:
        settings.gemini_api_key = "clave-falsa"
        gemini_mod._ULTIMO_MODELO_OK = None
        cargas = []

        def post_falso(url, json=None, timeout=None):
            cargas.append(json)
            return _RespFalsa('{"respuesta_texto": "hola"}')

        with patch.object(gemini_mod.requests, "post", post_falso):
            gemini_mod.generar_texto("Responde solo con la palabra hola.")
        config = cargas[0]["generationConfig"]
        caso("(c) generar_texto pide JSON con temperatura 0.3 y tope de 600",
             config.get("temperature") == 0.3
             and config.get("maxOutputTokens") == 600
             and config.get("response_mime_type") == "application/json",
             f"config={config}")
        cargas.clear()
        with patch.object(gemini_mod.requests, "post", post_falso):
            gemini_mod.transcribir_audio(b"audio-falso", "audio/ogg")
        config = cargas[0]["generationConfig"]
        caso("(c) El audio sigue en texto plano (sin JSON obligatorio)",
             "response_mime_type" not in config and config.get("temperature") == 0.3,
             f"config={config}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod._ULTIMO_MODELO_OK = modelo_viejo

    # ---- (d) El estado y el revisor en vivo (atender_mensaje) ----
    generar_viejo = agent_mod.generar_texto
    try:
        def generar_falso(prompt):
            return json.dumps({
                "respuesta_texto": "La limpieza cuesta $600, dura 60 minutos. "
                "¿Te la agendo para mañana a las 9:00?",
                "quiere_agendar": "no", "necesita_handoff": "no",
                "motivo_handoff": "", "foto_oficial_url_or_null": "",
                "nombre": "Jose Ramon", "motivo": "Quiere una limpieza",
                "fecha_cita": "",
            })

        agent_mod.generar_texto = generar_falso
        logic_mod._CITAS_PENDIENTES.clear()
        logic_mod._CITAS_PENDIENTES["5216694608263"] = dict(PROPUESTA)
        d = DepsV213(
            historial=[fila("cliente", "buenas noches"),
                       fila("robot", "¿Te la agendo para mañana a las 9:00?")],
        )
        atender_mensaje(d, "5216694608263", "Jose Ramon", "¿y la limpieza duele?",
                        con_ritmo=False,
                        ahora=datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc))
        mensaje_agente = d.mensajes_al_agente[0]
        caso("(d) El estado viaja en el mensaje al agente",
             "[Estado del cliente:" in mensaje_agente
             and '"etapa": "oferta_pendiente"' in mensaje_agente,
             f"mensaje={mensaje_agente[:200]}")
        caso("(d) En vivo: la oferta repetida se quita antes de mandar",
             d.textos_enviados and "¿Te la agendo" not in d.textos_enviados[0][1]
             and "$600" in d.textos_enviados[0][1],
             f"textos={d.textos_enviados}")
        caso("(d) La corrección queda en Diagnóstico (R1)",
             any(r["componente"] == "revision" and "R1" in r["detalle"]
                 for r in d.diagnostico),
             f"diagnostico={d.diagnostico}")
    finally:
        agent_mod.generar_texto = generar_viejo
        logic_mod._CITAS_PENDIENTES.clear()

    # (v3.4.11) R8: nunca afirmar una cita que no existe. En vivo el
    # robot dijo "ya estás apuntado" sin ninguna cita creada.
    estado_sin_cita = estado_cliente(
        [{"quien": "cliente", "mensaje": "quiero hacer una reservación"}],
        None, {}, "Ana")
    texto_r8, viol_r8 = revisar_respuesta(
        "Para tu blanqueamiento de mañana a las 09:00 ya estás apuntado. "
        "¿De qué otro servicio te gustaría saber el precio?",
        estado_sin_cita, "Ana", datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc))
    caso("(R8) Afirmación de cita inexistente se quita",
         "apuntado" not in texto_r8 and "R8" in viol_r8
         and "¿De qué otro servicio" in texto_r8,
         f"texto={texto_r8!r} violaciones={viol_r8}")
    texto_r8b, viol_r8b = revisar_respuesta(
        "Listo, ya estás apuntado para mañana a las 09:00.",
        estado_sin_cita, "Ana", datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc))
    caso("(R8b) Si era solo la afirmación, se ofrece confirmar con botones",
         texto_r8b == "¿Te la confirmo con botones para dejarla lista?"
         and "R8" in viol_r8b,
         f"texto={texto_r8b!r} violaciones={viol_r8b}")
    estado_con_cita = estado_cliente(
        [{"quien": "cliente", "mensaje": "¿a qué hora es mi cita?"}],
        None, {"estatus": "agendado", "fecha_cita": "2026-11-19T09:00:00-07:00"},
        "Ana")
    texto_ok, viol_ok = revisar_respuesta(
        "Tu cita quedó para mañana a las 09:00.",
        estado_con_cita, "Ana", datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc))
    caso("(R8c) Con cita creada, la frase pasa sin corrección",
         texto_ok == "Tu cita quedó para mañana a las 09:00." and "R8" not in viol_ok,
         f"texto={texto_ok!r} violaciones={viol_ok}")

    # (v3.4.11) Fechas con tolerancia: la hoja devolvía
    # "2026-11-19 9:00:00" (hora de un dígito) y el robot mostraba
    # el texto crudo al cliente. Ahora se lee y se dice bonito.
    caso("(fecha) La fecha de la hoja se dice bonita",
         formatear_cita_bonita("2026-11-19 9:00:00")
         == "jueves 19 de noviembre a las 09:00",
         f"bonita={formatear_cita_bonita('2026-11-19 9:00:00')!r}")
    caso("(fecha) La fecha normal sigue funcionando",
         formatear_cita_bonita("2026-11-19T09:00:00-07:00")
         == "jueves 19 de noviembre a las 09:00",
         "bonita cambió")
    caso("(fecha) Basura devuelve None, no explota",
         _parse_fecha_iso("no es una fecha") is None
         and _parse_fecha_iso("") is None,
         "el parser aceptó basura")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
