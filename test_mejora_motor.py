"""Mejora del motor (v3.20.7): memoria estructurada, IA decide la acción,
ciclo de vida y seguimiento proactivo.

Jose autorizó la mejora del motor con la visión de que el robot actúe
como una persona de recepción de clínica: coherente, con contexto,
memoria, conciencia de circunstancias y tiempo transcurrido, sin una
base de datos gigante. Esta batería cubre lo construido:

A. Memoria estructurada en Clientes: preferencias en la columna X
   "Preferencias" y acompañante/familia en la Y "Acompañante / familia"
   (agregadas AL FINAL, sin renombrar ni reordenar; K/L/N/O memoria,
   M calificación intocable, P robot_activo, W Miedos). Acumulación
   con dedupe, sin encabezado = no se escribe (compatibilidad), y
   Google caído = no lanza y deja rastro en Diagnóstico.
B. La IA declara la acción (accion/confianza en RespuestaAgente):
   "mover" ejecuta el cambio por el camino seguro si hay propuesta o
   cita futura (y confianza no baja); "pasar_persona" garantiza el
   handoff aunque no venga marcado; "agendar" garantiza quiere_agendar.
   Las invariantes (nunca confirmar sin propuesta, nunca inventar
   precios/descuentos, tope de 2 citas) no se tocan.
C. Ciclo de vida explícito en estado_cliente: nueva, activa,
   esperando, agendado, en_handoff, cerrada.
D. Contexto para la IA: línea "Estado de la conversación: ...",
   memoria estructurada (Preferencias con respaldo en notas,
   Acompañante) y "Pistas del sistema" (señales, no órdenes).
E. Seguimiento proactivo (robot/seguimiento.py): apagado por defecto;
   con el interruptor en SI solo sigue a clientes que preguntaron y
   no agendaron (sin cita, sin cerrar, sin handoff, robot activo,
   consentimiento SI, inactivos >3 días, sin seguimiento previo).

Uso:  python3 test_mejora_motor.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot import agent as agent_mod  # noqa: E402
from robot import estado as estado_mod  # noqa: E402
from robot import negocio as negocio_mod  # noqa: E402
from robot import seguimiento as seguimiento_mod  # noqa: E402
from robot import sheets as sheets_mod  # noqa: E402
from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import _BAJA_CONFIANZA, _CITAS_PENDIENTES, _RETOMAR  # noqa: E402
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO, H1, NOMBRE, TEL, _propuesta_base,
)
from test_simulacion_conversacional import (  # noqa: E402
    DepsConversacional, contexto_recibido, nuevo_c,
)
from test_simulacion_profunda import msg, propuesta_actual, todo_texto  # noqa: E402

RESULTADOS = []
AHORA = AHORA_ABIERTO


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()
    sheets_mod._CACHE.clear()


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


# ---------------------------------------------------------------------------
# Fakes de la capa Sheets (mismo patrón que test_auditoria_datos)
# ---------------------------------------------------------------------------

class _ReqFalso:
    def __init__(self, servicio, datos=None):
        self.servicio = servicio
        self.datos = datos

    def execute(self):
        self.servicio.llamadas += 1
        if (self.servicio.falla_en is not None
                and self.servicio.llamadas == self.servicio.falla_en):
            raise RuntimeError("Google caído (simulado)")
        return self.datos or {}


class _ValoresFalso:
    def __init__(self, servicio):
        self.servicio = servicio
        self.updates = []

    def update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        self.updates.append({"range": range, "values": body["values"]})
        return _ReqFalso(self.servicio, {})


class _ServicioFalso:
    def __init__(self, falla_en=None):
        self.falla_en = falla_en
        self.llamadas = 0
        self.valores = _ValoresFalso(self)

    def values(self):
        return self.valores


_FILAS_CLIENTES_BASE = {
    "fecha": "2026-11-24", "nombre": "Ana", "telefono": TEL,
    "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
    "estatus": "en conversacion", "handoff": "no",
    "ultima_actividad": "", "mensajes_totales": "3",
    "resumen_conversacion": "Preguntó por la limpieza.",
    "intereses": "Limpieza dental", "calificacion": "Tibio",
    "proxima_accion": "", "notas": "Solo en las mañanas",
    "robot_activo": "SI",
}


def _guardar_con_fila(fila, **kw):
    servicio = _ServicioFalso(falla_en=kw.pop("falla_en", None))
    diag = []
    try:
        with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
             patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila)]), \
             patch.object(sheets_mod, "registrar_diagnostico",
                          lambda *a, **k: diag.append(a)):
            sheets_mod.guardar_memoria_cliente(TEL, **kw)
        lanzo = False
    except Exception:
        lanzo = True
    return servicio, diag, lanzo


# ---------------------------------------------------------------------------
# A. Memoria estructurada (X Preferencias, Y Acompañante / familia)
# ---------------------------------------------------------------------------

def _a1():
    # Preferencias se acumulan en X (no en notas) y notas pasa intacta.
    fila = dict(_FILAS_CLIENTES_BASE,
                **{"Preferencias": "Solo en las mañanas",
                   "Acompañante / familia": ""})
    servicio, diag, lanzo = _guardar_con_fila(
        fila, resumen="Quiere limpieza", preferencias="Prefiere sábados")
    ups = {u["range"]: u["values"] for u in servicio.valores.updates}
    ok = (not lanzo and ups.get("Clientes!X2") == [["Solo en las mañanas; Prefiere sábados"]]
          and ups.get("Clientes!K2:O2") == [["Quiere limpieza", "Limpieza dental",
                                             "Tibio", "", "Solo en las mañanas"]])
    return ok, f"updates={servicio.valores.updates}"


def _a2():
    # Una preferencia que ya estaba no se duplica: no hay escritura X.
    fila = dict(_FILAS_CLIENTES_BASE,
                **{"Preferencias": "Solo en las mañanas",
                   "Acompañante / familia": ""})
    servicio, diag, lanzo = _guardar_con_fila(
        fila, preferencias="Solo en las mañanas")
    ups = [u["range"] for u in servicio.valores.updates]
    ok = not lanzo and "Clientes!X2" not in ups
    return ok, f"updates={ups}"


def _a3():
    # Sin encabezado X (hoja vieja), no se escribe nada y no lanza.
    fila = dict(_FILAS_CLIENTES_BASE)  # sin clave "Preferencias"
    servicio, diag, lanzo = _guardar_con_fila(
        fila, preferencias="Prefiere sábados")
    ups = [u["range"] for u in servicio.valores.updates]
    ok = not lanzo and "Clientes!X2" not in ups
    return ok, f"updates={ups}"


def _a4():
    # Acompañante se guarda en Y y se acumula sin duplicar.
    fila = dict(_FILAS_CLIENTES_BASE,
                **{"Preferencias": "", "Acompañante / familia": ""})
    servicio, diag, lanzo = _guardar_con_fila(
        fila, acompanante="Viene con su hija")
    ups = {u["range"]: u["values"] for u in servicio.valores.updates}
    ok = (not lanzo and ups.get("Clientes!Y2") == [["Viene con su hija"]])
    return ok, f"updates={servicio.valores.updates}"


def _a5():
    # Google caído desde la primera escritura: no lanza y deja rastro.
    fila = dict(_FILAS_CLIENTES_BASE,
                **{"Preferencias": "", "Acompañante / familia": ""})
    servicio, diag, lanzo = _guardar_con_fila(
        fila, falla_en=1, preferencias="Prefiere sábados")
    ok = not lanzo and len(diag) == 1
    return ok, f"lanzo={lanzo} diag={diag}"


# ---------------------------------------------------------------------------
# B. La IA declara la acción (agent._normalizar)
# ---------------------------------------------------------------------------

def _b1():
    r = agent_mod._normalizar({
        "respuesta_texto": "Claro.",
        "acompanante": "Viene con su hija",
    })
    return r.acompanante == "Viene con su hija", f"acompanante={r.acompanante!r}"


def _b2():
    r = agent_mod._normalizar({
        "respuesta_texto": "Claro.",
        "accion": "mover",
        "confianza": "alta",
    })
    ok = r.accion == "mover" and r.confianza == "alta"
    return ok, f"accion={r.accion!r} confianza={r.confianza!r}"


def _b3():
    r = agent_mod._normalizar({
        "respuesta_texto": "Te paso con una persona.",
        "accion": "pasar_persona",
    })
    return r.necesita_handoff == "si", f"handoff={r.necesita_handoff!r}"


def _b4():
    r = agent_mod._normalizar({
        "respuesta_texto": "Claro, te agendo.",
        "accion": "agendar",
        "fecha_cita": H1,
    })
    return r.quiere_agendar == "si", f"quiere={r.quiere_agendar!r}"


# ---------------------------------------------------------------------------
# C. Ciclo de vida explícito (estado_cliente)
# ---------------------------------------------------------------------------

def _estado(historial=None, propuesta=None, cliente=None):
    return estado_mod.estado_cliente(
        historial or [], propuesta, cliente or {}, NOMBRE, ahora=AHORA)


def _c1():
    e = _estado()
    return e["ciclo_vida"] == "nueva", f"ciclo={e['ciclo_vida']}"


def _c2():
    e = _estado(historial=[{"quien_hablo": "cliente", "mensaje": "hola",
                            "motivo": "", "fecha": "2026-11-23T10:00:00"}])
    return e["ciclo_vida"] == "activa", f"ciclo={e['ciclo_vida']}"


def _c3():
    e = _estado(propuesta=_propuesta_base(AHORA))
    return e["ciclo_vida"] == "esperando", f"ciclo={e['ciclo_vida']}"


def _c4():
    e = _estado(cliente={"fecha_cita": "2026-12-01T10:00:00",
                         "estatus": "agendado"})
    return e["ciclo_vida"] == "agendado", f"ciclo={e['ciclo_vida']}"


def _c5():
    e = _estado(cliente={"proxima_accion": "cerrada"})
    return e["ciclo_vida"] == "cerrada", f"ciclo={e['ciclo_vida']}"


def _c6():
    e = _estado(historial=[
        {"quien_hablo": "cliente", "mensaje": "quiero hablar con alguien",
         "motivo": "", "fecha": "2026-11-23T10:00:00"},
        {"quien_hablo": "robot", "mensaje": "Te paso con una persona.",
         "motivo": "handoff", "fecha": "2026-11-23T10:01:00"},
    ])
    return e["ciclo_vida"] == "en_handoff", f"ciclo={e['ciclo_vida']}"


# ---------------------------------------------------------------------------
# D. Integración: la IA decide la acción y el contexto la acompaña
# ---------------------------------------------------------------------------

def _d1():
    # accion="mover" con propuesta pendiente: el sistema ejecuta el
    # cambio por el camino seguro (borra propuesta, pregunta nuevo día).
    # El mensaje NO dispara el gate determinista de cambio: la ruta
    # que se prueba es la de la acción declarada por la IA.
    d = nuevo_c(propuesta=_propuesta_base(AHORA))
    d.agente_override = RespuestaAgente(
        respuesta_texto="Claro, te cambio la cita.", accion="mover",
        confianza="alta")
    msg(d, "puedo cambiar el día de mi cita")
    ok = (propuesta_actual() is None and "qué día" in todo_texto(d).lower()
          and not d.citas)
    return ok, (f"propuesta={propuesta_actual() is not None} "
                f"texto={todo_texto(d)[:100]!r} citas={d.citas}")


def _d2():
    # accion="mover" sin nada que mover: sigue el flujo normal.
    d = nuevo_c()
    d.agente_override = RespuestaAgente(
        respuesta_texto="Claro, ¿qué día te viene mejor?", accion="mover",
        confianza="alta")
    r = msg(d, "hola")
    ok = bool(r.get("respondio")) and bool(d.textos)
    return ok, f"textos={d.textos} r={r}"


def _d3():
    # accion="mover" con confianza baja: NO se mueve nada (la IA no
    # está segura); la propuesta se queda viva.
    d = nuevo_c(propuesta=_propuesta_base(AHORA))
    d.agente_override = RespuestaAgente(
        respuesta_texto="¿Me confirmas qué día prefieres?", accion="mover",
        confianza="baja")
    msg(d, "puedo cambiar el día de mi cita")
    ok = propuesta_actual() is not None and bool(d.textos)
    return ok, f"propuesta={propuesta_actual() is not None} texto={todo_texto(d)[:100]!r}"


def _d4():
    # accion="pasar_persona" sin necesita_handoff: el sistema
    # garantiza el handoff (correo + mensaje al cliente). Con
    # monotonic=100 se simula la máquina recién encendida (el bug
    # v3.20.7: el primer correo se descartaba como "repetido").
    d = nuevo_c()
    d.agente_override = RespuestaAgente(
        respuesta_texto="Te paso con una persona, un momento por favor.",
        accion="pasar_persona", necesita_handoff="no")
    with patch("robot.logic.time.monotonic", lambda: 100.0):
        r = msg(d, "hola")
    ok = r.get("handoff") is True and len(d.alertas_handoff) == 1
    return ok, f"r={r} alertas={len(d.alertas_handoff)}"


def _d4b():
    # Bug v3.20.7 (directo): con la máquina recién encendida
    # (monotonic < ventana de 30 min), el primer correo de handoff
    # NO es repetido; el segundo dentro de la ventana SÍ lo es.
    from robot import logic as logic_mod

    d = nuevo_c()
    with patch("robot.logic.time.monotonic", lambda: 100.0):
        primero = logic_mod._handoff_repetido(d, TEL, "Pide persona")
        segundo = logic_mod._handoff_repetido(d, TEL, "Pide persona")
    ok = primero is False and segundo is True
    return ok, f"primero={primero} segundo={segundo}"


def _d5():
    # accion="agendar" sin quiere_agendar: el sistema lo garantiza y
    # se crea la propuesta con botones (nunca la cita directa).
    d = nuevo_c()
    d.agente_override = RespuestaAgente(
        respuesta_texto="Claro, te propongo una cita.", accion="agendar",
        quiere_agendar="no", fecha_cita=H1, motivo="Limpieza dental")
    msg(d, "el jueves a las 10 por favor")
    ok = propuesta_actual() is not None and bool(d.botones) and not d.citas
    return ok, (f"propuesta={propuesta_actual() is not None} "
                f"botones={d.botones} citas={d.citas}")


def _d6():
    # El contexto trae el ciclo de vida explícito.
    d = nuevo_c()
    msg(d, "hola")
    ok = contexto_recibido(d, "Estado de la conversación: nueva")
    return ok, "no llegó la línea de ciclo de vida al contexto"


def _d7():
    # Memoria estructurada en el contexto: Preferencias (X) y
    # Acompañante (Y) llegan a la IA sin adivinar.
    d = nuevo_c(cliente={
        "nombre": NOMBRE, "telefono": TEL, "motivo": "Limpieza",
        "estatus": "en conversacion",
        "Preferencias": "Solo en las mañanas",
        "Acompañante / familia": "Viene con su hija",
    })
    msg(d, "hola")
    ok = (contexto_recibido(d, "Prefiere Solo en las mañanas")
          and contexto_recibido(d, "Acompañante/familia: Viene con su hija"))
    return ok, "la memoria estructurada no llegó al contexto"


def _d8():
    # Pistas del sistema: el mensaje parece pedir agendar.
    d = nuevo_c()
    msg(d, "quiero agendar una cita")
    ok = (contexto_recibido(d, "Pistas del sistema")
          and contexto_recibido(d, "parece pedir agendar"))
    return ok, "la pista de agendar no llegó al contexto"


def _d9():
    # Respaldo: preferencias viejas en notas (O) se siguen leyendo
    # aunque la columna X no traiga nada.
    d = nuevo_c(cliente={
        "nombre": NOMBRE, "telefono": TEL, "motivo": "Limpieza",
        "estatus": "en conversacion", "notas": "Solo en las tardes",
    })
    msg(d, "hola")
    ok = contexto_recibido(d, "Prefiere Solo en las tardes")
    return ok, "el respaldo de notas no llegó al contexto"


# ---------------------------------------------------------------------------
# E. Seguimiento proactivo
# ---------------------------------------------------------------------------

class _DepsSeguimiento:
    def __init__(self, clientes, historiales):
        self._clientes = clientes
        self._historiales = historiales
        self.plantillas = []
        self.registros = []

    def leer_clientes(self):
        return self._clientes

    def leer_historial(self, telefono):
        return self._historiales.get(telefono, [])

    def enviar_plantilla(self, telefono, plantilla, idioma, parametros):
        self.plantillas.append((telefono, plantilla, idioma, parametros))

    def registrar_conversacion(self, fecha, telefono, quien, mensaje,
                               respondio, motivo=""):
        self.registros.append((telefono, motivo))


_AHORA_SEG = datetime(2026, 11, 24, 10, 0, 0)


def _cliente_base(**kw):
    c = {
        "telefono": "521000000001", "nombre": "Ana", "motivo": "Limpieza",
        "fecha_cita": "", "estatus": "en conversacion", "handoff": "no",
        "proxima_accion": "", "robot_activo": "SI",
        "Consentimiento_mensajes": "SI",
    }
    c.update(kw)
    return c


def _historia(fecha, con_seguimiento=False):
    filas = [
        {"fecha": "2026-11-19T09:00:00", "quien_hablo": "cliente",
         "mensaje": "¿cuánto cuesta la limpieza?", "motivo": ""},
        {"fecha": fecha, "quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600.", "motivo": ""},
    ]
    if con_seguimiento:
        filas.append({"fecha": fecha, "quien_hablo": "robot",
                      "mensaje": "(seguimiento proactivo)", "motivo": "seguimiento"})
    return filas


def _e1():
    # Interruptor apagado: no se manda nada, ni se lee la hoja.
    d = _DepsSeguimiento([_cliente_base()], {"521000000001": _historia("2026-11-19T10:00:00")})
    orig = seguimiento_mod.seguimiento_activo
    seguimiento_mod.seguimiento_activo = lambda: False
    try:
        r = seguimiento_mod.enviar_seguimientos_pendientes(d, ahora=_AHORA_SEG)
    finally:
        seguimiento_mod.seguimiento_activo = orig
    ok = r == {"enviados": 0, "fallidos": 0} and not d.plantillas
    return ok, f"r={r} plantillas={d.plantillas}"


def _e2():
    # Interruptor encendido: el cliente elegible recibe la plantilla
    # y queda registrado con motivo "seguimiento".
    d = _DepsSeguimiento([_cliente_base()], {"521000000001": _historia("2026-11-19T10:00:00")})
    orig_act = seguimiento_mod.seguimiento_activo
    orig_cfg = negocio_mod.configuracion
    seguimiento_mod.seguimiento_activo = lambda: True
    negocio_mod.configuracion = lambda: {}
    try:
        r = seguimiento_mod.enviar_seguimientos_pendientes(d, ahora=_AHORA_SEG)
    finally:
        seguimiento_mod.seguimiento_activo = orig_act
        negocio_mod.configuracion = orig_cfg
    ok = (r["enviados"] == 1 and len(d.plantillas) == 1
          and d.plantillas[0][1] == "seguimiento_no_agendo"
          and d.plantillas[0][3] == ["Ana", "Limpieza"]
          and d.registros == [("521000000001", "seguimiento")])
    return ok, f"r={r} plantillas={d.plantillas} registros={d.registros}"


def _e3():
    # Solo pasa el que preguntó y quedó a medias: sin cita, sin
    # cerrar, sin handoff, robot activo, consentimiento SI, inactivo
    # >3 días y sin seguimiento previo.
    elegible = _cliente_base(telefono="521000000001")
    excluidos = [
        _cliente_base(telefono="521000000002", Consentimiento_mensajes="NO"),
        _cliente_base(telefono="521000000003", fecha_cita="2026-11-25T10:00:00"),
        _cliente_base(telefono="521000000004", proxima_accion="cerrada"),
        _cliente_base(telefono="521000000005", handoff="si"),
        _cliente_base(telefono="521000000006", robot_activo="NO"),
        _cliente_base(telefono="521000000007", estatus="agendado"),
        _cliente_base(telefono="521000000008"),  # activo ayer
        _cliente_base(telefono="521000000009"),  # ya recibió seguimiento
    ]
    historiales = {f"52100000000{i}": _historia("2026-11-19T10:00:00")
                   for i in range(1, 10)}
    historiales["521000000008"] = _historia("2026-11-23T10:00:00")
    historiales["521000000009"] = _historia("2026-11-19T10:00:00", con_seguimiento=True)
    d = _DepsSeguimiento([elegible] + excluidos, historiales)
    elegidos = seguimiento_mod.clientes_para_seguimiento(d, _AHORA_SEG)
    tels = [c["telefono"] for c in elegidos]
    ok = tels == ["521000000001"]
    return ok, f"elegidos={tels}"


def _e4():
    # El interruptor por defecto es NO: vacío en Configuración = apagado.
    orig = negocio_mod.interruptor
    negocio_mod.interruptor = lambda clave, defecto="SI": defecto
    try:
        activo = seguimiento_mod.seguimiento_activo()
    finally:
        negocio_mod.interruptor = orig
    return activo is False, f"activo={activo}"


def main():
    print("== Mejora del motor (v3.20.7) ==")
    caso("A1 preferencias se acumulan en X y notas pasa intacta", _a1)
    caso("A2 preferencia repetida no se duplica", _a2)
    caso("A3 sin encabezado X no se escribe ni lanza", _a3)
    caso("A4 acompañante se guarda en Y", _a4)
    caso("A5 Google caído: sin lanzar y con rastro", _a5)
    caso("B1 _normalizar parsea acompanante", _b1)
    caso("B2 _normalizar conserva accion mover y confianza", _b2)
    caso("B3 accion pasar_persona marca handoff", _b3)
    caso("B4 accion agendar marca quiere_agendar", _b4)
    caso("C1 ciclo_vida nueva sin historial", _c1)
    caso("C2 ciclo_vida activa con historial", _c2)
    caso("C3 ciclo_vida esperando con propuesta", _c3)
    caso("C4 ciclo_vida agendado con cita futura", _c4)
    caso("C5 ciclo_vida cerrada manda", _c5)
    caso("C6 ciclo_vida en_handoff tras pase a persona", _c6)
    caso("D1 accion mover con propuesta ejecuta el cambio", _d1)
    caso("D2 accion mover sin nada sigue el flujo normal", _d2)
    caso("D3 accion mover con confianza baja no mueve nada", _d3)
    caso("D4 accion pasar_persona garantiza el handoff", _d4)
    caso("D4b primer correo tras reinicio no es repetido", _d4b)
    caso("D5 accion agendar garantiza la propuesta", _d5)
    caso("D6 contexto trae el ciclo de vida", _d6)
    caso("D7 contexto trae memoria estructurada", _d7)
    caso("D8 contexto trae pista de agendar", _d8)
    caso("D9 respaldo: preferencias viejas en notas", _d9)
    caso("E1 interruptor apagado: no manda nada", _e1)
    caso("E2 interruptor encendido: manda y registra", _e2)
    caso("E3 solo sigue a los que quedaron a medias", _e3)
    caso("E4 el interruptor por defecto es NO", _e4)

    fallas = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallas)}/{len(RESULTADOS)} casos OK")
    if fallas:
        print("Fallaron:")
        for n in fallas:
            print(f"  - {n}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
