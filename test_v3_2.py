"""Pruebas de la versión 3.2 (memoria), SIN internet.

Lo nuevo de la v3.2:
(a) Memoria del cliente: el agente devuelve en su JSON lo que aprendió
    (resumen, interés, próxima acción, preferencias) y logic.py lo guarda
    en Clientes (K, L, N, O). En el siguiente mensaje, el contexto lleva
    "Lo que sabes de este cliente", ANTES del historial reciente.
(b) Memoria de apartados: si el robot le aparta el lugar a un cliente
    con una propuesta activa, el apartado queda guardado en Propuestas
    (columnas nuevas G apartado, H aparta_hasta) y el contexto lo recuerda.
(c) Revisor R7: el robot no cierra con la misma frase de su último
    mensaje ("Quedamos a tus órdenes" tres veces seguidas en vivo).

Uso:  python test_v3_2.py
"""

from datetime import datetime, timezone
from unittest.mock import patch

import robot.agent as agent_mod
import robot.logic as logic_mod
import robot.sheets as sheets_mod
from robot.agent import RespuestaAgente, guion
from robot.logic import atender_mensaje
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
TELEFONO = "5216694608263"
# Viernes 13 de noviembre de 2026, 00:05 hora de Mazatlán.
VIERNES = datetime(2026, 11, 13, 7, 5, tzinfo=timezone.utc)


def fila(quien, mensaje, motivo=""):
    return {"fecha": "2026-11-13T04:00:00+00:00", "telefono": TELEFONO,
            "quien_hablo": quien, "mensaje": mensaje, "robot_respondio": "si",
            "motivo": motivo}


class DepsV32:
    """Servicios de mentira, con memoria de cliente."""

    def __init__(self, historial=None, respuesta_agente=None, cliente=None):
        self.historial = historial or []
        self.respuesta_agente = respuesta_agente
        self.cliente = cliente
        self.memoria = {}
        self.propuestas_guardadas = {}
        self.conversaciones = []
        self.textos_enviados = []
        self.botones_enviados = []
        self.diagnostico = []
        self.mensajes_al_agente = []

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
        m = self.memoria.setdefault(telefono, {})
        if resumen:
            m["resumen_conversacion"] = resumen
        if interes:
            m["intereses"] = interes
        if proxima_accion:
            m["proxima_accion"] = proxima_accion
        if preferencias:
            viejo = m.get("notas", "")
            if preferencias.lower() not in viejo.lower():
                m["notas"] = (viejo + "; " + preferencias).strip("; ") if viejo else preferencias

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

    def crear_cita(self, nombre, telefono, motivo, fecha_cita, nota=""):
        return {"inicio": fecha_cita}

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha, resumen=""):
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


class _ValoresFalso:
    def __init__(self):
        self.updates = []

    def update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        self.updates.append({"range": range, "values": body["values"]})
        return self

    def execute(self):
        return {}


class _ServicioFalso:
    def __init__(self):
        self.valores = _ValoresFalso()

    def values(self):
        return self.valores


FILA_CLIENTE = {
    "fecha": "2026-11-13", "nombre": "Jose Ramon", "telefono": TELEFONO,
    "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
    "estatus": "en conversacion", "handoff": "no",
    "ultima_actividad": "", "mensajes_totales": "3",
    "resumen_conversacion": "Preguntó por la limpieza.",
    "intereses": "Limpieza dental", "calificacion": "Tibio",
    "proxima_accion": "", "notas": "Solo en las mañanas",
    "robot_activo": "SI",
}


def main():
    # ---- (a) El agente devuelve memoria en su JSON ----
    r = agent_mod._normalizar({
        "respuesta_texto": "La limpieza cuesta $600.",
        "resumen_cliente": "Quiere una limpieza, le duele la muela.",
        "interes_cliente": "Limpieza dental",
        "proxima_accion": "Espera confirmación sábado 10:00",
        "preferencias": "Solo en las mañanas",
    })
    caso("(a) El JSON del agente trae resumen, interés, próxima acción y preferencias",
         r.resumen_cliente == "Quiere una limpieza, le duele la muela."
         and r.interes_cliente == "Limpieza dental"
         and r.proxima_accion == "Espera confirmación sábado 10:00"
         and r.preferencias == "Solo en las mañanas",
         f"salió: {r}")
    r = agent_mod._normalizar({"respuesta_texto": "Hola."})
    caso("(a) Sin campos de memoria, quedan vacíos (no se inventa nada)",
         r.resumen_cliente == "" and r.interes_cliente == ""
         and r.proxima_accion == "" and r.preferencias == "")
    g = " ".join(guion().split())
    caso("(a) El guion pide los 4 campos de memoria en el JSON",
         "resumen_cliente" in g and "interes_cliente" in g
         and "proxima_accion" in g and "preferencias" in g)
    caso("(a) El guion dice que use lo que ya sabe del cliente",
         "no vuelvas a preguntar lo que ya sabes" in g.lower())

    # ---- (a) sheets.guardar_memoria_cliente ----
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana",
                      lambda pestana: [dict(FILA_CLIENTE)]):
        sheets_mod.guardar_memoria_cliente(
            TELEFONO, resumen="Quiere limpieza y blanqueamiento.",
            interes="Blanqueamiento", proxima_accion="Confirmar sábado 10:00",
            preferencias="Prefiere sábados")
    caso("(a) La memoria se escribe en Clientes K:O, sin tocar la calificación",
         len(servicio.valores.updates) == 1
         and servicio.valores.updates[0]["range"] == "Clientes!K2:O2"
         and servicio.valores.updates[0]["values"][0] == [
             "Quiere limpieza y blanqueamiento.", "Blanqueamiento", "Tibio",
             "Confirmar sábado 10:00", "Solo en las mañanas; Prefiere sábados"],
         f"salió: {servicio.valores.updates}")
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana",
                      lambda pestana: [dict(FILA_CLIENTE)]):
        sheets_mod.guardar_memoria_cliente(TELEFONO, resumen="Nuevo resumen.")
    caso("(a) Un campo vacío no borra lo que ya había",
         servicio.valores.updates[0]["values"][0] == [
             "Nuevo resumen.", "Limpieza dental", "Tibio", "", "Solo en las mañanas"],
         f"salió: {servicio.valores.updates}")
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana",
                      lambda pestana: [dict(FILA_CLIENTE)]):
        sheets_mod.guardar_memoria_cliente(TELEFONO, preferencias="Solo en las mañanas")
    caso("(a) Una preferencia que ya estaba no se duplica",
         servicio.valores.updates == [],
         f"salió: {servicio.valores.updates}")
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana", lambda pestana: []):
        sheets_mod.guardar_memoria_cliente(TELEFONO, resumen="Hola.")
    caso("(a) Sin fila de cliente, no se escribe nada",
         servicio.valores.updates == [])

    # ---- (a) Lógica: la memoria se guarda y se lee al día siguiente ----
    deps = DepsV32(
        historial=[fila("cliente", "¿cuánto cuesta la limpieza?")],
        respuesta_agente=RespuestaAgente(
            respuesta_texto="La limpieza cuesta $600, dura 60 minutos.",
            motivo="Limpieza dental",
            resumen_cliente="Quiere una limpieza, le duele la muela.",
            interes_cliente="Limpieza dental",
            proxima_accion="Espera que le ofrezcan cita",
            preferencias="Solo en las mañanas",
            modelo="falso"))
    atender_mensaje(deps, TELEFONO, "Jose Ramon", "¿cuánto cuesta la limpieza?",
                    ahora=VIERNES, con_ritmo=False)
    caso("(a) Tras responder, la memoria del cliente quedó guardada",
         deps.memoria.get(TELEFONO, {}).get("resumen_conversacion")
         == "Quiere una limpieza, le duele la muela."
         and deps.memoria[TELEFONO].get("intereses") == "Limpieza dental"
         and deps.memoria[TELEFONO].get("notas") == "Solo en las mañanas",
         f"salió: {deps.memoria}")
    deps.respuesta_agente = RespuestaAgente(
        respuesta_texto="¡Hola de nuevo, Jose Ramon! ¿Seguimos con la limpieza?",
        modelo="falso")
    atender_mensaje(deps, TELEFONO, "Jose Ramon", "hola, soy yo de nuevo",
                    ahora=datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc),
                    con_ritmo=False)
    caso("(a) Al día siguiente, el contexto lleva lo que sabe del cliente",
         any("Lo que sabes de este cliente" in m
             and "le duele la muela" in m
             and "Solo en las mañanas" in m
             for m in deps.mensajes_al_agente),
         f"salió: {deps.mensajes_al_agente}")

    # ---- (a2) Cliente que vuelve: saludo con memoria, no como nuevo ----
    deps2 = DepsV32(
        historial=[fila("cliente", "¿cuánto cuesta la limpieza?"),
                   fila("robot", "La limpieza cuesta $600.")],
        respuesta_agente=RespuestaAgente(
            respuesta_texto="¡Hola! ¿Seguimos con la limpieza?",
            modelo="falso"))
    atender_mensaje(deps2, TELEFONO, "Jose Ramon", "hola",
                    ahora=datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc),
                    con_ritmo=False)
    caso("(a2) Cliente que vuelve: el contexto lo recuerda, no lo trata como nuevo",
         any("ya ha hablado contigo antes" in m or "no escribía" in m
             or "desde su último mensaje" in m or "recordando de qué hablaban" in m
             for m in deps2.mensajes_al_agente),
         f"salió: {deps2.mensajes_al_agente}")

    deps3 = DepsV32(
        respuesta_agente=RespuestaAgente(
            respuesta_texto="¡Hola! ¿En qué te ayudo?",
            modelo="falso"))
    atender_mensaje(deps3, TELEFONO, "", "hola",
                    ahora=VIERNES, con_ritmo=False)
    caso("(a2) Cliente nuevo: el contexto no lo trata como regreso",
         all("ya ha hablado contigo antes" not in m and "no escribía" not in m
             for m in deps3.mensajes_al_agente),
         f"salió: {deps3.mensajes_al_agente}")

    # (a3) Cliente que vuelve y PREGUNTA algo: se responde eso primero,
    # el saludo de regreso no tapa la pregunta (v3.4.6).
    deps4 = DepsV32(
        historial=[fila("cliente", "¿cuánto cuesta la limpieza?"),
                   fila("robot", "La limpieza cuesta $600.")],
        respuesta_agente=RespuestaAgente(
            respuesta_texto="Estamos en Av. del Mar 123, en Mazatlán.",
            modelo="falso"))
    atender_mensaje(deps4, TELEFONO, "Jose Ramon", "¿y dónde están?",
                    ahora=VIERNES, con_ritmo=False)
    caso("(a3) Cliente que vuelve y pregunta: responde su pregunta primero",
         any("Responde su pregunta actual primero" in m
             for m in deps4.mensajes_al_agente),
         f"salió: {deps4.mensajes_al_agente}")

    # ---- (b) Memoria de apartados ----
    logic_mod._CITAS_PENDIENTES.clear()
    propuesta = {
        "nombre": "Jose Ramon", "motivo": "Limpieza dental",
        "fecha_cita": "2026-11-14T10:00:00", "fecha_bonita": "sábado 14 de noviembre a las 10:00",
        "creado_en": "2026-11-13T07:00:00+00:00",
    }
    logic_mod._CITAS_PENDIENTES[TELEFONO] = dict(propuesta)
    deps = DepsV32(
        historial=[fila("cliente", "¿cuánto cuesta la limpieza?"),
                   fila("robot", "La limpieza cuesta $600. ¿Te la agendo para mañana sábado a las 10:00?")],
        respuesta_agente=RespuestaAgente(
            respuesta_texto="Claro, piénsalo con calma. Te aparto el lugar hasta mañana "
                            "sin compromiso, ¿te parece?",
            modelo="falso"))
    atender_mensaje(deps, TELEFONO, "Jose Ramon", "lo voy a pensar",
                    ahora=VIERNES, con_ritmo=False)
    guardada = deps.propuestas_guardadas.get(TELEFONO, {})
    caso("(b) El apartado queda guardado en la propuesta, hasta mañana sábado 14",
         guardada.get("apartado") == "si"
         and guardada.get("aparta_hasta") == "mañana sábado 14",
         f"salió: {guardada}")
    deps.respuesta_agente = RespuestaAgente(
        respuesta_texto="Claro, tu lugar sigue apartado hasta mañana sábado 14. ¿Te lo confirmo?",
        modelo="falso")
    atender_mensaje(deps, TELEFONO, "Jose Ramon", "hola, ¿todavía me tienes apartado el lugar?",
                    ahora=datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc),
                    con_ritmo=False)
    caso("(b) Al día siguiente, el contexto recuerda el apartado",
         any("apartaste el lugar hasta mañana sábado 14" in m
             for m in deps.mensajes_al_agente),
         f"salió: {deps.mensajes_al_agente}")
    logic_mod._CITAS_PENDIENTES.clear()

    # ---- (b) Propuestas: las columnas nuevas viajan en la fila ----
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana",
                      lambda pestana: [{"telefono": TELEFONO}]):
        sheets_mod.guardar_propuesta(TELEFONO, {
            "nombre": "Jose Ramon", "motivo": "Limpieza",
            "fecha_cita": "2026-11-14T10:00:00",
            "fecha_bonita": "sábado 14 de noviembre a las 10:00",
            "creado_en": "2026-11-13T07:00:00+00:00",
            "apartado": "si", "aparta_hasta": "mañana sábado 14"})
    caso("(b) guardar_propuesta escribe A:I con apartado y aparta_hasta",
         len(servicio.valores.updates) == 1
         and servicio.valores.updates[0]["range"] == "Propuestas!A2:I2"
         and servicio.valores.updates[0]["values"][0][6:8] == ["si", "mañana sábado 14"],
         f"salió: {servicio.valores.updates}")

    # ---- (c) R7: no repetir el cierre ----
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600, dura 60 minutos. Quedamos a tus órdenes.",
        {"etapa": "pregunto", "ultimo_mensaje_robot": "¿Te ayudo con algo? Quedamos a tus órdenes."},
        telefono=TELEFONO)
    caso("(c) R7: el cierre repetido se quita, el resto queda",
         texto == "La limpieza cuesta $600, dura 60 minutos." and v == ["R7"],
         f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600, dura 60 minutos. ¿Te ayudo con algo más?",
        {"etapa": "pregunto", "ultimo_mensaje_robot": "¿Te ayudo con algo? Quedamos a tus órdenes."},
        telefono=TELEFONO)
    caso("(c) R7: un cierre distinto no se toca",
         "¿Te ayudo con algo más?" in texto and v == [], f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "Quedamos a tus órdenes.",
        {"etapa": "pregunto", "ultimo_mensaje_robot": "Quedamos a tus órdenes."},
        telefono=TELEFONO)
    caso("(c) R7: si la respuesta ERA solo el cierre, se cambia por una pregunta",
         texto == "¿Te ayudo con algo más?" and v == ["R7"], f"salió: {texto!r} {v}")
    texto, v = revisar_respuesta(
        "La limpieza cuesta $600. Quedamos a tus órdenes.",
        {"etapa": "pregunto"},
        telefono=TELEFONO)
    caso("(c) R7: sin último mensaje del robot, no se quita nada",
         "Quedamos a tus órdenes." in texto and v == [], f"salió: {texto!r} {v}")

    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos PASS (test_v3_2)")
    if fallos:
        print("FALLOS:", fallos)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
