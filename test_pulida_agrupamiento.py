"""Pulida agrupamiento/handoff/botones (v3.20.3).

Cubre los encargos de la pulida profunda del motor de agrupamiento,
el handoff y los botones:
- Kill-switch global también frena los botones (salvo hablar con
  persona, que es el camino al humano).
- El correo de handoff siempre trae el hilo de la conversación
  (botón, silencio con la IA apagada) y app.py lo pasa a mail.
- Doble toque en Confirmar nunca duplica la cita (ni secuencial ni
  concurrente): candado por teléfono en atender_mensaje/atender_boton.
- Orden: un texto en el buzón se procesa ANTES que un toque de botón
  (flush en app.py); el Agrupador junta en orden, ignora duplicados
  y no pierde mensajes que llegan durante el procesamiento.
- Wamids con desalojo FIFO (no se borran todos al pasar el tope).
- "Dejarla igual" viejo no promete persona sin avisar; con propuesta
  real sí manda el correo de handoff.
- R11 con valor exacto: solo los porcentajes literales del
  Conocimiento; mecánicas (2x1, rebaja) solo si están literales.
- Typos inequívocos nuevos: desagendar/desagenda (cancelar),
  pospon (cambiar), con sus negaciones.
- Escenarios adversariales: 5 mensajes contradictorios, botón viejo,
  pide persona y luego escribe, cancela y luego confirma.

Uso:  python3 test_pulida_agrupamiento.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente  # noqa: E402
from robot.agrupar import Agrupador  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _intencion_cambio,
    atender_boton,
    atender_mensaje,
)
from robot.revision import (  # noqa: E402
    precios_de_conocimiento,
    revisar_respuesta,
    texto_conocimiento,
)
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    CONOCIMIENTO,
    DepsDinamica,
    H1,
    H2,
    NOMBRE,
    TEL,
    _fila_espejo,
    _propuesta_base,
)

AHORA = AHORA_ABIERTO
PRECIOS = precios_de_conocimiento(CONOCIMIENTO)
TEXTO_CONOC = texto_conocimiento(CONOCIMIENTO)
FRASE_SEGURA = "Déjame confirmarlo con el encargado y te aviso en un momento."

RESULTADOS = []


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()


def caso(nombre, fn):
    limpiar()
    try:
        ok, detalle = fn()
    except Exception as exc:
        ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok))
    marca = "PASS" if ok else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not ok else ""))
    limpiar()


class DepsAgrupamiento(DepsDinamica):
    """DepsDinamica con control configurable, handoff completo y
    retardo opcional en el espejo (para forzar la carrera del doble
    toque)."""

    def __init__(self, *args, control=None, activo="SI", retardo_espejo=0.0, **kw):
        super().__init__(*args, **kw)
        self.control = control or {"bot_activo": "SI", "ultima_respuesta_humana": ""}
        self.activo = activo
        self.retardo_espejo = retardo_espejo
        self.handoffs = []
        self.mensajes_agente = []
        self.respuesta_fija = None

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_agente.append(mensaje or "")
        if self.respuesta_fija is not None:
            return self.respuesta_fija
        return super().preguntar_agente(mensaje, conocimiento, fotos, historial)

    def leer_control(self):
        return dict(self.control)

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias="", miedos=""):
        self.memorias.append({"resumen": resumen, "interes": interes,
                              "proxima_accion": proxima_accion,
                              "preferencias": preferencias, "miedos": miedos})

    def leer_robot_activo(self, telefono):
        return self.activo

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha,
                       resumen="", hilo=""):
        self.alertas_handoff.append(motivo)
        self.handoffs.append({
            "nombre": nombre, "telefono": telefono, "motivo": motivo,
            "mensaje": mensaje, "fecha": fecha, "resumen": resumen, "hilo": hilo,
        })

    def leer_citas_espejo(self):
        if self.retardo_espejo:
            time.sleep(self.retardo_espejo)
        return super().leer_citas_espejo()


def nuevo(clase=DepsAgrupamiento, espejo=None, historial=None, cliente=None,
          propuesta=None, ahora=AHORA_ABIERTO, **kw):
    d = clase(espejo=espejo, historial=historial, cliente=cliente, ahora=ahora, **kw)
    if propuesta is not None:
        _CITAS_PENDIENTES[TEL] = dict(propuesta)
    return d


def todo_texto(d):
    return " ".join(d.textos + [b[0] for b in d.botones])


def _historia():
    return [
        {"fecha": "2026-11-23T15:00:00+00:00", "quien_hablo": "cliente",
         "mensaje": "quiero una cita para limpieza"},
        {"fecha": "2026-11-23T15:01:00+00:00", "quien_hablo": "robot",
         "mensaje": "Te propongo tu cita para el lunes a las 10:00."},
        {"fecha": "2026-11-23T15:02:00+00:00", "quien_hablo": "cliente",
         "mensaje": "me da miedo, ¿duele?"},
    ]


# ---------------------------------------------------------------------------
# A. Kill-switch global también frena los botones
# ---------------------------------------------------------------------------

def _a1():
    d = nuevo(control={"bot_activo": "NO", "ultima_respuesta_humana": ""},
              propuesta=_propuesta_base(AHORA))
    r = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = (len(d.citas) == 0 and r.get("respondio") is False
          and TEL not in _CITAS_PENDIENTES)
    return ok, f"citas={d.citas} r={r} pendiente={TEL in _CITAS_PENDIENTES}"


def _a2():
    d = nuevo(control={"bot_activo": "NO", "ultima_respuesta_humana": ""},
              propuesta=_propuesta_base(AHORA))
    r = atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    ok = r.get("handoff") is True and len(d.handoffs) == 1
    return ok, f"r={r} handoffs={d.handoffs}"


def _a3():
    d = nuevo(propuesta=_propuesta_base(AHORA))
    r = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = len(d.citas) == 1 and r.get("respondio") is True
    return ok, f"citas={d.citas} r={r}"


# ---------------------------------------------------------------------------
# B. El correo de handoff siempre trae el hilo
# ---------------------------------------------------------------------------

def _b1():
    cliente = {"estatus": "en conversacion", "motivo": "limpieza",
               "nombre": NOMBRE, "resumen_conversacion": "Preguntó precios."}
    d = nuevo(historial=_historia(), cliente=cliente,
              propuesta=_propuesta_base(AHORA))
    atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    if len(d.handoffs) != 1:
        return False, f"handoffs={d.handoffs}"
    h = d.handoffs[0]
    ok = ("me da miedo" in h["hilo"] and "Te propongo tu cita" in h["hilo"]
          and h["resumen"] == "Preguntó precios.")
    return ok, f"hilo={h['hilo']!r} resumen={h['resumen']!r}"


def _b2():
    # IA apagada para este cliente: una urgencia igual manda el correo,
    # y el correo trae el hilo.
    d = nuevo(historial=_historia(), activo="NO")
    r = atender_mensaje(d, TEL, NOMBRE, "me duele mucho, es urgente",
                        con_ritmo=False, ahora=AHORA)
    if len(d.handoffs) != 1:
        return False, f"r={r} handoffs={d.handoffs}"
    h = d.handoffs[0]
    ok = r.get("handoff") is True and "me da miedo" in h["hilo"]
    return ok, f"r={r} hilo={h['hilo']!r}"


def _b3():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"),
               encoding="utf-8").read()
    ok = ('def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, '
          'fecha, resumen="", hilo="")' in src
          and "mail.alerta_handoff(nombre, telefono, motivo, ultimo_mensaje, "
              "fecha, resumen, hilo)" in src)
    return ok, "app.py no pasa hilo a mail.alerta_handoff"


# ---------------------------------------------------------------------------
# C. Doble toque: nunca duplicar la cita
# ---------------------------------------------------------------------------

def _c1():
    d = nuevo(propuesta=_propuesta_base(AHORA))
    atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    r2 = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = len(d.citas) == 1 and r2.get("respondio") is True
    return ok, f"citas={len(d.citas)} r2={r2}"


def _c2():
    # Carrera real: dos hilos tocan Confirmar a la vez y el espejo
    # tarda (ensancha la ventana entre leer la propuesta y borrarla).
    d = nuevo(propuesta=_propuesta_base(AHORA), retardo_espejo=0.4)
    errores = []

    def tocar():
        try:
            atender_boton(d, TEL, NOMBRE, "confirmar_cita",
                          con_ritmo=False, ahora=AHORA)
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=tocar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)
    vivos = [h for h in hilos if h.is_alive()]
    ok = not vivos and not errores and len(d.citas) == 1
    return ok, f"citas={len(d.citas)} vivos={len(vivos)} errores={errores}"


def _c3():
    # Confirmar y Cambiar a la vez: una sola salida consistente, sin
    # excepción y sin duplicar.
    d = nuevo(propuesta=_propuesta_base(AHORA), retardo_espejo=0.3)
    errores = []

    def tocar(boton):
        try:
            atender_boton(d, TEL, NOMBRE, boton, con_ritmo=False, ahora=AHORA)
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=tocar, args=(b,))
             for b in ("confirmar_cita", "cambiar_hora")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)
    ok = not errores and len(d.citas) <= 1
    return ok, f"citas={len(d.citas)} errores={errores} textos={d.textos}"


# ---------------------------------------------------------------------------
# D. Orden: el texto en el buzón va ANTES que el botón
# ---------------------------------------------------------------------------

def _d1():
    # Simula lo que hace app.py con el fix: el texto que está en el
    # buzón (debounce) se procesa primero; el botón actúa después.
    d = nuevo(propuesta=_propuesta_base(AHORA))
    lotes = []

    def cb(tel, nom, textos, wamids):
        lotes.append(list(textos))
        atender_mensaje(d, tel, nom, "\n".join(textos), con_ritmo=False, ahora=AHORA)

    ag = Agrupador(cb, espera_segundos=60)
    ag.agregar(TEL, "no, mejor cancela", wamid="w-cancel")
    # El cliente toca Confirmar con el texto todavía en el buzón:
    # primero se vacía el buzón (la cancelación gana), luego el botón.
    ag.procesar_ahora(TEL)
    r = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = (lotes == [["no, mejor cancela"]] and len(d.citas) == 0
          and "cancelada" in todo_texto(d).lower())
    return ok, f"lotes={lotes} citas={d.citas} textos={d.textos} r={r}"


def _d2():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"),
               encoding="utf-8").read()
    i_flush = src.find("_AGRUPADOR.procesar_ahora(telefono)")
    i_boton = src.find("atender_boton(_DEPS, telefono, nombre, boton_id)")
    ok = 0 <= i_flush < i_boton
    return ok, f"flush={i_flush} boton={i_boton}"


def _d3():
    lotes = []
    ag = Agrupador(lambda t, n, tx, w: lotes.append(list(tx)), espera_segundos=60)
    ok1 = ag.agregar(TEL, "uno", wamid="a")
    ok2 = ag.agregar(TEL, "dos", wamid="b")
    dup = ag.agregar(TEL, "uno otra vez", wamid="a")
    procesado = ag.procesar_ahora(TEL)
    ok = ok1 and ok2 and dup is False and procesado and lotes == [["uno", "dos"]]
    return ok, f"lotes={lotes} dup={dup} procesado={procesado}"


def _d4():
    # Un mensaje que llega mientras el lote anterior se está
    # procesando NO se pierde ni se mezcla: va como lote nuevo.
    orden = []
    listo = threading.Event()

    def cb(tel, nom, textos, wamids):
        orden.append(list(textos))
        if len(orden) == 1:
            listo.wait(5)

    ag = Agrupador(cb, espera_segundos=0.05)
    ag.agregar(TEL, "primero", wamid="w1")
    time.sleep(0.2)  # el primer lote ya está procesando (bloqueado)
    ag.agregar(TEL, "segundo", wamid="w2")
    time.sleep(0.2)  # su timer dispara y se reprograma (2 s)
    listo.set()
    time.sleep(2.6)  # el reprogramado procesa el segundo lote
    ok = orden == [["primero"], ["segundo"]]
    return ok, f"orden={orden}"


# ---------------------------------------------------------------------------
# E. Wamids con desalojo FIFO
# ---------------------------------------------------------------------------

def _e1():
    ag = Agrupador(lambda t, n, tx, w: None, espera_segundos=60, max_vistos=3)
    for w in ("a", "b", "c", "d"):
        ag.agregar(TEL, f"msg {w}", wamid=w)
    viejo = ag.agregar(TEL, "msg a otra vez", wamid="a")   # ya se desalojó
    reciente = ag.agregar(TEL, "msg d otra vez", wamid="d")  # sigue conocido
    ok = viejo is True and reciente is False
    return ok, f"viejo={viejo} reciente={reciente}"


# ---------------------------------------------------------------------------
# F. "Dejarla igual": toque viejo y correo de handoff
# ---------------------------------------------------------------------------

def _f1():
    # Toque viejo: ya no hay propuesta. No promete persona (no hay
    # correo), responde con calma.
    d = nuevo()
    r = atender_boton(d, TEL, NOMBRE, "dejar_cita_igual", con_ritmo=False, ahora=AHORA)
    txt = " ".join(d.textos)
    ok = ("Te paso con una persona" not in txt and len(d.handoffs) == 0
          and r.get("respondio") is True)
    return ok, f"textos={d.textos} handoffs={d.handoffs} r={r}"


def _f2():
    # Con propuesta de adelanto: sí promete persona, así que sí manda
    # el correo de handoff.
    p = _propuesta_base(AHORA, tipo="adelanto")
    d = nuevo(propuesta=p)
    r = atender_boton(d, TEL, NOMBRE, "dejar_cita_igual", con_ritmo=False, ahora=AHORA)
    ok = (len(d.handoffs) == 1 and "queda como está" in todo_texto(d)
          and TEL not in _CITAS_PENDIENTES)
    return ok, f"handoffs={d.handoffs} textos={d.textos} r={r}"


def _f3():
    # mover=True (oferta por tope): sin promesa de persona, sin correo.
    p = _propuesta_base(AHORA, tipo="mover")
    d = nuevo(propuesta=p)
    atender_boton(d, TEL, NOMBRE, "dejar_cita_igual", con_ritmo=False, ahora=AHORA)
    ok = (len(d.handoffs) == 0 and "Te paso con una persona" not in todo_texto(d)
          and "queda como está" in todo_texto(d))
    return ok, f"handoffs={d.handoffs} textos={d.textos}"


# ---------------------------------------------------------------------------
# G. R11 con valor exacto del descuento
# ---------------------------------------------------------------------------

def _conoc_descuento():
    return [
        {"tipo": "faq", "pregunta_o_servicio": "¿Manejan descuentos?",
         "respuesta_o_precio": "Sí, tenemos 20% de descuento los martes y 2x1 en limpieza.",
         "detalle": ""},
        {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
         "respuesta_o_precio": "$600", "detalle": ""},
    ]


def _rev_descuento(txt, conoc):
    return revisar_respuesta(
        txt, {}, "", ahora=AHORA, telefono=TEL,
        precios_conocidos=precios_de_conocimiento(conoc),
        texto_conocimiento=texto_conocimiento(conoc))


def _g1():
    conoc = _conoc_descuento()
    permitido, v_ok = _rev_descuento("Te hago un 20% de descuento si vienes el martes.", conoc)
    inventado, v_bad = _rev_descuento("Te hago un 15% de descuento si vienes hoy.", conoc)
    ok = (v_ok == [] and "20%" in permitido
          and v_bad == ["R11"] and inventado == FRASE_SEGURA)
    return ok, f"ok={permitido!r} v_ok={v_ok} bad={inventado!r} v_bad={v_bad}"


def _g2():
    conoc = [{"tipo": "faq", "pregunta_o_servicio": "¿Manejan descuentos?",
              "respuesta_o_precio": "Manejamos descuentos para estudiantes.",
              "detalle": ""}]
    txt, v = _rev_descuento("Te hago un 10% de descuento.", conoc)
    ok = v == ["R11"] and txt == FRASE_SEGURA
    return ok, f"txt={txt!r} v={v}"


def _g3():
    conoc = _conoc_descuento()
    dosx1, v_2x1 = _rev_descuento("Tenemos 2x1 en limpieza los martes.", conoc)
    rebaja, v_reb = _rev_descuento("Te aplico una rebaja especial.", conoc)
    ok = (v_2x1 == [] and "2x1" in dosx1
          and v_reb == ["R11"] and rebaja == FRASE_SEGURA)
    return ok, f"2x1={dosx1!r} v={v_2x1} rebaja={rebaja!r} v={v_reb}"


def _g4():
    # Sin mención de descuentos en el Conocimiento: cualquier
    # descuento se desecha (comportamiento v3.20.2 intacto).
    txt, v = _rev_descuento("Te hago un 20% de descuento.", CONOCIMIENTO)
    ok = v == ["R11"] and txt == FRASE_SEGURA
    return ok, f"txt={txt!r} v={v}"


# ---------------------------------------------------------------------------
# H. Typos inequívocos nuevos
# ---------------------------------------------------------------------------

def _h1():
    ok = (_intencion_cambio("desagendar mi cita") == "cancelar"
          and _intencion_cambio("desagenda la cita") == "cancelar")
    return ok, ""


def _h2():
    ok = (_intencion_cambio("pospon la cita") == "cambiar"
          and _intencion_cambio("mejor posponla") == "cambiar")
    return ok, ""


def _h3():
    ok = (_intencion_cambio("no desagendar") is None
          and _intencion_cambio("no posponer") is None
          and _intencion_cambio("no quiero desagendar") is None)
    return ok, ""


# ---------------------------------------------------------------------------
# I. Escenarios adversariales
# ---------------------------------------------------------------------------

def _i1():
    # 5 mensajes contradictorios en un solo lote: no se rompe, no
    # crea citas, responde una sola vez.
    d = nuevo()
    texto = ("quiero una cita el martes\nno el martes no\n"
             "mejor el miércoles\nya no\nel miércoles sí")
    r = atender_mensaje(d, TEL, NOMBRE, texto, con_ritmo=False, ahora=AHORA)
    ok = r.get("respondio") is True and len(d.citas) == 0
    return ok, f"r={r} citas={d.citas} textos={d.textos}"


def _i2():
    # Botón viejo de Confirmar (sin propuesta): no crea nada y
    # responde con calma, nunca silencio.
    d = nuevo()
    r = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = len(d.citas) == 0 and r.get("respondio") is True and len(d.textos) == 1
    return ok, f"citas={d.citas} textos={d.textos} r={r}"


def _i3():
    # Botón viejo de Adelantar (sin propuesta): responde, nunca aire.
    d = nuevo()
    r = atender_boton(d, TEL, NOMBRE, "adelantar_cita", con_ritmo=False, ahora=AHORA)
    ok = r.get("respondio") is True and len(d.textos) == 1 and len(d.citas) == 0
    return ok, f"textos={d.textos} r={r}"


def _i4():
    # Pide persona (botón) y luego vuelve a escribir: handoff con
    # correo; el mensaje siguiente, con pausa humana activa, queda
    # registrado en silencio sin romperse.
    d = nuevo(historial=_historia(), propuesta=_propuesta_base(AHORA))
    r1 = atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    d.control = {"bot_activo": "SI",
                 "ultima_respuesta_humana": AHORA.isoformat()}
    r2 = atender_mensaje(d, TEL, NOMBRE, "hola, ¿ya me atienden?",
                         con_ritmo=False, ahora=AHORA)
    ok = (r1.get("handoff") is True and len(d.handoffs) == 1
          and r2.get("respondio") is False
          and any(c["quien"] == "cliente" for c in d.conversaciones))
    return ok, f"r1={r1} r2={r2} handoffs={len(d.handoffs)}"


def _i5():
    # Cancela y luego toca Confirmar (botón viejo): la cancelación
    # ganó; el botón viejo no crea nada.
    cliente = {"estatus": "agendado", "fecha_cita": H2,
               "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00")]
    d = nuevo(espejo=espejo, cliente=cliente)
    r1 = atender_mensaje(d, TEL, NOMBRE, "cancela mi cita",
                         con_ritmo=False, ahora=AHORA)
    r2 = atender_boton(d, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    ok = (r1.get("cita_cancelada") is True and len(d.citas_canceladas) == 1
          and len(d.citas) == 0)
    return ok, f"r1={r1} r2={r2} citas={d.citas} canceladas={d.citas_canceladas}"


def _i6():
    # Pide persona con la IA apagada para él: el handoff igual se
    # resuelve (correo + caso marcado), sin respuesta al cliente.
    d = nuevo(activo="NO")
    r = atender_mensaje(d, TEL, NOMBRE, "quiero hablar con una persona",
                        con_ritmo=False, ahora=AHORA)
    ok = r.get("handoff") is True and len(d.handoffs) == 1 and len(d.textos) == 0
    return ok, f"r={r} handoffs={d.handoffs} textos={d.textos}"


# ---------------------------------------------------------------------------
# J. Miedos estructurados (propuesta 1): columna W en Clientes
# ---------------------------------------------------------------------------

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


_FILA_BASE = {
    "fecha": "2026-11-24", "nombre": "Ana", "telefono": TEL,
    "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
    "estatus": "en conversacion", "handoff": "no",
    "ultima_actividad": "", "mensajes_totales": "3",
    "resumen_conversacion": "Preguntó por la limpieza.",
    "intereses": "Limpieza dental", "calificacion": "Tibio",
    "proxima_accion": "", "notas": "Solo en las mañanas",
    "robot_activo": "SI",
}


def _j1():
    # El agente devuelve miedos en su JSON y logic los guarda.
    from robot import agent as agent_mod
    r = agent_mod._normalizar({
        "respuesta_texto": "Claro, sin problema.",
        "miedos": "le dan miedo las agujas",
    })
    if r.miedos != "le dan miedo las agujas":
        return False, f"_normalizar miedos={r.miedos!r}"
    d = nuevo()
    d.respuesta_fija = RespuestaAgente(
        respuesta_texto="Claro, sin problema.",
        miedos="le dan miedo las agujas")
    atender_mensaje(d, TEL, NOMBRE, "me dan miedo las agujas",
                    con_ritmo=False, ahora=AHORA)
    ok = bool(d.memorias) and d.memorias[-1].get("miedos") == "le dan miedo las agujas"
    return ok, f"memorias={d.memorias}"


def _j2():
    # Con la columna W poblada, el contexto del agente la incluye.
    cliente = {"estatus": "en conversacion", "nombre": NOMBRE,
               "Miedos / sensibilidades": "le dan miedo las agujas"}
    d = nuevo(cliente=cliente)
    atender_mensaje(d, TEL, NOMBRE, "hola", con_ritmo=False, ahora=AHORA)
    ok = any("Le dan miedo" in m for m in d.mensajes_agente)
    return ok, (d.mensajes_agente[-1][:300] if d.mensajes_agente else "sin mensajes")


def _j3():
    # Sin la columna (hoja vieja), nada se rompe y no se menciona.
    cliente = {"estatus": "en conversacion", "nombre": NOMBRE}
    d = nuevo(cliente=cliente)
    atender_mensaje(d, TEL, NOMBRE, "hola", con_ritmo=False, ahora=AHORA)
    ok = bool(d.textos) and not any("Le dan miedo" in m for m in d.mensajes_agente)
    return ok, f"textos={d.textos}"


def _j4():
    # sheets: con encabezado, el miedo va a W2 y se acumula; sin
    # encabezado, no se escribe nada (compatibilidad hacia atrás).
    from unittest.mock import patch
    from robot import sheets as sheets_mod
    fila_con = dict(_FILA_BASE, **{"Miedos / sensibilidades": "le dan miedo las agujas"})
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila_con)]):
        sheets_mod.guardar_memoria_cliente(TEL, miedos="le dan miedo el dolor")
    ok = (len(servicio.valores.updates) == 1
          and servicio.valores.updates[0]["range"] == "Clientes!W2"
          and servicio.valores.updates[0]["values"] == [
              ["le dan miedo las agujas; le dan miedo el dolor"]])
    if not ok:
        return False, f"salió: {servicio.valores.updates}"
    servicio2 = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio2), \
         patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(_FILA_BASE)]):
        sheets_mod.guardar_memoria_cliente(TEL, miedos="le dan miedo las agujas")
    ok2 = servicio2.valores.updates == []
    return ok2, f"sin encabezado salió: {servicio2.valores.updates}"


def _j5():
    # sheets: un miedo que ya estaba no se duplica.
    from unittest.mock import patch
    from robot import sheets as sheets_mod
    fila_con = dict(_FILA_BASE, **{"Miedos / sensibilidades": "le dan miedo las agujas"})
    servicio = _ServicioFalso()
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila_con)]):
        sheets_mod.guardar_memoria_cliente(TEL, miedos="Le dan miedo las agujas")
    ok = servicio.valores.updates == []
    return ok, f"salió: {servicio.valores.updates}"


def main():
    caso("A1 kill-switch global: Confirmar no crea cita", _a1)
    caso("A2 kill-switch global: hablar con persona sigue", _a2)
    caso("A3 control normal: Confirmar sí crea", _a3)
    caso("B1 handoff por botón trae hilo y resumen", _b1)
    caso("B2 handoff en silencio trae hilo", _b2)
    caso("B3 app.py pasa hilo a mail.alerta_handoff", _b3)
    caso("C1 doble toque secuencial: una sola cita", _c1)
    caso("C2 doble toque concurrente: una sola cita", _c2)
    caso("C3 confirmar+cambiar concurrentes: consistente", _c3)
    caso("D1 texto en buzón se procesa antes que el botón", _d1)
    caso("D2 app.py vacía el buzón antes del botón", _d2)
    caso("D3 Agrupador junta en orden e ignora duplicados", _d3)
    caso("D4 mensaje durante procesamiento no se pierde", _d4)
    caso("E1 wamids con desalojo FIFO", _e1)
    caso("F1 dejarla viejo: sin promesa falsa", _f1)
    caso("F2 dejarla con propuesta: manda correo", _f2)
    caso("F3 dejarla mover: sin correo ni promesa", _f3)
    caso("G1 R11 valor exacto permitido/inventado", _g1)
    caso("G2 R11 sin % en Conocimiento: % inventado", _g2)
    caso("G3 R11 mecánicas solo si están literales", _g3)
    caso("G4 R11 sin descuentos en Conocimiento", _g4)
    caso("H1 desagendar/desagenda = cancelar", _h1)
    caso("H2 pospon = cambiar", _h2)
    caso("H3 negaciones de los typos nuevos", _h3)
    caso("I1 5 mensajes contradictorios en un lote", _i1)
    caso("I2 botón viejo confirmar: sin cita, con respuesta", _i2)
    caso("I3 botón viejo adelantar: nunca silencio", _i3)
    caso("I4 pide persona y luego escribe (pausa)", _i4)
    caso("I5 cancela y luego confirma: no crea nada", _i5)
    caso("I6 pide persona con IA apagada: handoff resuelto", _i6)
    caso("J1 agente devuelve miedos y logic los guarda", _j1)
    caso("J2 contexto incluye miedos de la columna W", _j2)
    caso("J3 sin columna W: nada se rompe", _j3)
    caso("J4 sheets escribe W2 y respeta hoja vieja", _j4)
    caso("J5 sheets no duplica un miedo ya guardado", _j5)

    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok "
          f"(pulida agrupamiento)")
    if fallos:
        print("FALLOS:", ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
