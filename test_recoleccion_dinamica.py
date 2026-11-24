"""Recolección dinámica de datos (v3.20.9): el robot usa lo que el
cliente confirma (nombre, número, correo, preferencias) sin volver
a pedirlo y sin usar nunca el nombre del dueño.

Jose pidió: verificar que la recolección sea dinámica e inteligente —
cuando la persona confirme su nombre, números, correo y preferencias,
el agente lo use (llamarlo por su nombre, proponer en su horario
preferido, etc.), sin pedir dos veces lo mismo y sin usar nunca el
nombre del dueño.

Esta batería cubre lo construido:

A. Nombre dinámico: el confirmado persiste en Clientes (columna B,
   vía actualizar_nombre_cliente) y manda sobre el de perfil de
   WhatsApp en el contexto y en estado_cliente; fusionar_cliente
   ya no lo pisa con el perfil; respaldo por regex ("me llamo X").
B. Números dinámicos: el número de registro persiste en las Notas
   del espejo ("Teléfono de registro: X") y se lee de vuelta para
   no volver a pedirlo, prellenar propuestas y registrar citas al
   número dado.
C. Correo (nuevo): columna Z "Correo" en Clientes; captura por la
   IA (respuesta.correo) o por regex; se guarda y va en el contexto;
   el guion manda pedirlo solo cuando es relevante, en texto, y
   confirmar de vuelta lo dado.
D. Preferencias/miedos/acompañante: verificados de punta a punta
   (guardar → leer → contexto) con cliente que vuelve.
E. G7 (batería dorada): el ejemplo del guion ya no enseña la
   deflexión; la regla es explícita; R14 en el revisor reemplaza
   una deflexión sin precios por la lista real del Conocimiento
   (nunca inventa: sin servicios con precio, no se aplica).
F. G4 (documentado, sin cambio de código): la batería dorada es
   más estricta que el guion vigente — el guion permite recordar
   la propuesta en una frase corta (test_v2_12 lo afirma). El
   robot siguió el guion; no es un bug.
G. G18 (convertido de repro_g18.py): confirmar por botón pide
   nombre y número después de confirmar.

G15/G17 de la batería dorada fueron fallas técnicas de Gemini
(no contestó tras reintentar), no bugs de contenido: se re-corren
en la Mac de Jose, sin fix inventado.

Uso:  python3 test_recoleccion_dinamica.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import robot.agent as agente_mod  # noqa: E402
import robot.sheets as sheets_mod  # noqa: E402
from robot.agent import RespuestaAgente, _normalizar  # noqa: E402
from robot.estado import estado_cliente  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _extraer_correo,
    _extraer_nombre,
    _telefono_registro_conocido,
)
from robot.revision import revisar_respuesta, servicios_de_conocimiento  # noqa: E402
from robot.sheets import fusionar_cliente  # noqa: E402
from test_bateria_dinamica import AHORA_ABIERTO, H1, NOMBRE, TEL  # noqa: E402
from test_simulacion_conversacional import (  # noqa: E402
    DepsConversacional,
    contexto_recibido,
)
from test_simulacion_profunda import btn, msg, propuesta_actual, todo_texto  # noqa: E402

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
# Deps con registro de la recolección dinámica
# ---------------------------------------------------------------------------

class DepsRecoleccion(DepsConversacional):
    """DepsConversacional + registro de nombres/correos/notas guardados."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nombres_actualizados = []
        self.correos_guardados = []
        self.notas_actualizadas = []

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias="", miedos="",
                                acompanante="", correo=""):
        self.memorias.append({"resumen": resumen, "interes": interes,
                              "proxima_accion": proxima_accion,
                              "preferencias": preferencias,
                              "miedos": miedos, "acompanante": acompanante})
        if correo:
            self.correos_guardados.append(correo)

    def actualizar_nombre_cliente(self, telefono, nombre):
        self.nombres_actualizados.append((telefono, nombre))

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        self.notas_actualizadas.append((telefono, fecha_cita, notas))


def nuevo_r(espejo=None, historial=None, cliente=None, propuesta=None,
            ahora=AHORA_ABIERTO, agente=None):
    d = DepsRecoleccion(espejo=espejo, historial=historial, cliente=cliente,
                        ahora=ahora)
    d.agente_override = agente
    if propuesta is not None:
        _CITAS_PENDIENTES[TEL] = dict(propuesta)
    return d


def _cliente_base(**extra):
    fila = {
        "fecha": "2026-11-24", "nombre": "Ana", "telefono": TEL,
        "motivo": "Limpieza", "fecha_cita": "", "origen": "whatsapp",
        "estatus": "en conversacion", "handoff": "no",
        "ultima_actividad": "", "mensajes_totales": "3",
        "resumen_conversacion": "", "intereses": "", "calificacion": "",
        "proxima_accion": "", "notas": "", "robot_activo": "SI",
    }
    fila.update(extra)
    return fila


def _propuesta(nombre="Jose Ramon", telefono_registro=""):
    return {
        "nombre": nombre, "motivo": "Limpieza dental",
        "fecha_cita": H1, "fecha_bonita": "lunes 23 de noviembre a las 09:00",
        "creado_en": "2026-11-23T10:00:00-07:00", "profesional": "",
        "nombre_paciente": "", "relacion_paciente": "",
        "numero_paciente": telefono_registro, "cita2": None, "urgencia": "",
    }


# ---------------------------------------------------------------------------
# Fakes de la capa Sheets (mismo patrón que test_mejora_motor)
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
# A. Nombre dinámico
# ---------------------------------------------------------------------------

def _a1():
    # fusionar: el nombre existente (confirmado) manda sobre el perfil.
    viejo = {"fecha": "2026-11-12", "nombre": "María López", "telefono": TEL,
             "motivo": "Quiere cita", "fecha_cita": "", "origen": "whatsapp",
             "estatus": "en conversacion", "handoff": "no"}
    nuevo = {"fecha": "2026-11-13", "nombre": "María", "telefono": TEL,
             "motivo": "Preguntó precios", "fecha_cita": "", "origen": "whatsapp",
             "estatus": "en conversacion", "handoff": "no"}
    fusion = fusionar_cliente(viejo, nuevo)
    return fusion[1] == "María López", f"fusion={fusion}"


def _a2():
    # fusionar: si la fila no tenía nombre, entra el nuevo.
    viejo = {"fecha": "2026-11-12", "nombre": "", "telefono": TEL,
             "motivo": "Quiere cita", "fecha_cita": "", "origen": "whatsapp",
             "estatus": "en conversacion", "handoff": "no"}
    nuevo = {"fecha": "2026-11-13", "nombre": "Ana", "telefono": TEL,
             "motivo": "Preguntó precios", "fecha_cita": "", "origen": "whatsapp",
             "estatus": "en conversacion", "handoff": "no"}
    fusion = fusionar_cliente(viejo, nuevo)
    return fusion[1] == "Ana", f"fusion={fusion}"


def _a3():
    # El nombre confirmado por la IA se escribe en Clientes (B).
    d = nuevo_r(agente=RespuestaAgente(
        respuesta_texto="¡Perfecto, María López!", nombre="María López"))
    msg(d, "soy María López")
    ok = (TEL, "María López") in d.nombres_actualizados
    return ok, f"nombres={d.nombres_actualizados}"


def _a4():
    # El contexto saluda con el nombre confirmado, no con el de perfil.
    d = nuevo_r(cliente=_cliente_base(nombre="María López"))
    msg(d, "hola")
    ok = contexto_recibido(d, "El cliente se llama María López")
    return ok, f"mensajes={d.mensajes_agente[-1:] if d.mensajes_agente else []}"


def _a5():
    # Respaldo regex: "me llamo X" se captura aunque la IA no lo extraiga.
    d = nuevo_r(agente=RespuestaAgente(respuesta_texto="¡Mucho gusto!"))
    msg(d, "me llamo Ana García")
    ok = (TEL, "Ana García") in d.nombres_actualizados
    return ok, f"nombres={d.nombres_actualizados}"


def _a6():
    # El regex es conservador: no captura frases que no son nombre.
    ok = (_extraer_nombre("me llamo Ana García") == "Ana García"
          and _extraer_nombre("mi nombre es Juan") == "Juan"
          and _extraer_nombre("me llamó la atención el precio") == ""
          and _extraer_nombre("me llamo la atención") == ""
          and _extraer_nombre("mi hermana se llama Ana") == ""
          and _extraer_nombre("hola") == "")
    return ok, "regex de nombre"


def _a7():
    # estado_cliente prefiere el nombre de Clientes sobre el perfil.
    estado = estado_cliente(
        [], None, {"nombre": "María López", "estatus": "en conversacion"},
        "María", ahora=AHORA)
    return estado["nombre"] == "María López", f"estado={estado['nombre']!r}"


def _a8():
    # actualizar_nombre_cliente escribe directo en Clientes!B.
    servicio = _ServicioFalso()
    fila = _cliente_base(nombre="María")
    with patch.object(sheets_mod, "_servicio_sheets", lambda: servicio), \
         patch.object(sheets_mod, "leer_pestana", lambda pestana: [dict(fila)]):
        sheets_mod.actualizar_nombre_cliente(TEL, "María López")
    ups = {u["range"]: u["values"] for u in servicio.valores.updates}
    ok = ups.get("Clientes!B2") == [["María López"]]
    return ok, f"updates={servicio.valores.updates}"


# ---------------------------------------------------------------------------
# B. Números dinámicos
# ---------------------------------------------------------------------------

_ESPEJO_CON_NUMERO = [{
    "Teléfono": TEL, "Estado": "Confirmada", "Fecha": "2026-11-25",
    "Notas": "Paciente: Jose Ramon | Teléfono de registro: 6671234567",
}]


def _b1():
    # El número de registro se lee de vuelta desde las Notas del espejo.
    class _Deps:
        def leer_citas_espejo(self):
            return list(_ESPEJO_CON_NUMERO)
    numero = _telefono_registro_conocido(_Deps(), TEL)
    return numero == "6671234567", f"numero={numero!r}"


def _b2():
    # Con nombre y número conocidos, confirmar NO vuelve a pedirlos.
    d = nuevo_r(espejo=list(_ESPEJO_CON_NUMERO),
                propuesta=_propuesta(nombre="María López"))
    btn(d, "confirmar_cita")
    ok = len(d.citas) == 1 and "¿me das tu nombre completo" not in todo_texto(d)
    return ok, f"citas={d.citas} texto={todo_texto(d)[:150]!r}"


def _b3():
    # La propuesta se prellena con el número conocido de citas pasadas.
    d = nuevo_r(espejo=list(_ESPEJO_CON_NUMERO),
                propuesta=_propuesta())
    msg(d, "hola")
    p = propuesta_actual() or {}
    ok = p.get("telefono_registro") == "6671234567"
    return ok, f"propuesta={p.get('telefono_registro')!r}"


def _b4():
    # Número dado en texto libre (sin propuesta) queda en el espejo.
    d = nuevo_r(espejo=[{
        "Teléfono": TEL, "Estado": "Confirmada", "Fecha": "2026-11-25",
        "Notas": "Paciente: Jose Ramon",
    }])
    msg(d, "regístralo al 6679998888")
    ok = any("Teléfono de registro: 6679998888" in n[2] for n in d.notas_actualizadas)
    return ok, f"notas={d.notas_actualizadas}"


# ---------------------------------------------------------------------------
# C. Correo (nuevo)
# ---------------------------------------------------------------------------

def _c1():
    ok = (_extraer_correo("mi correo es Ana@Example.COM") == "ana@example.com"
          and _extraer_correo("sin correo aquí") == "")
    return ok, "regex de correo"


def _c2():
    r = _normalizar({"respuesta_texto": "x", "correo": "ana@example.com"})
    return r.correo == "ana@example.com", f"correo={r.correo!r}"


def _c3():
    # guardar_memoria_cliente escribe el correo en Clientes!Z si hay encabezado.
    fila = _cliente_base(**{"Correo": ""})
    servicio, diag, lanzo = _guardar_con_fila(fila, correo="ana@example.com")
    ups = {u["range"]: u["values"] for u in servicio.valores.updates}
    ok = (not lanzo and ups.get("Clientes!Z2") == [["ana@example.com"]])
    # Sin encabezado Z, no se escribe nada (compatibilidad hacia atrás).
    fila_sin = _cliente_base()
    servicio2, diag2, lanzo2 = _guardar_con_fila(fila_sin, correo="ana@example.com")
    ups2 = [u["range"] for u in servicio2.valores.updates]
    ok = ok and (not lanzo2 and "Clientes!Z2" not in ups2)
    return ok, f"updates={servicio.valores.updates} ups2={ups2}"


def _c4():
    # El contexto incluye el correo confirmado.
    d = nuevo_r(cliente=_cliente_base(**{"Correo": "ana@example.com"}))
    msg(d, "hola")
    ok = contexto_recibido(d, "Su correo es ana@example.com")
    return ok, "contexto con correo"


def _c5():
    # El correo que da la IA se guarda en Clientes vía la memoria.
    d = nuevo_r(agente=RespuestaAgente(
        respuesta_texto="Perfecto, te lo envío.", correo="ana@example.com"))
    msg(d, "mi correo es ana@example.com")
    ok = d.correos_guardados == ["ana@example.com"]
    return ok, f"correos={d.correos_guardados}"


def _c6():
    # El guion manda pedir el correo solo si es relevante y confirmar
    # de vuelta lo dado (sincronizado en agent.py y guion-robot.md).
    g = agente_mod.guion()
    texto_md = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "guion-robot.md"), encoding="utf-8").read()
    ok = ("lo registro con ese correo" in g
          and "acompanante, correo, partes" in g
          and "lo registro con ese correo" in texto_md)
    return ok, "guion de correo"


# ---------------------------------------------------------------------------
# D. Preferencias / miedos / acompañante: guardar → leer → usar
# ---------------------------------------------------------------------------

def _d1():
    # El contexto trae preferencias, miedos y acompañante de Clientes.
    d = nuevo_r(cliente=_cliente_base(
        **{"Preferencias": "mañanas", "Miedos / sensibilidades": "las agujas",
           "Acompañante / familia": "su hija"}))
    msg(d, "hola")
    ok = (contexto_recibido(d, "Prefiere mañanas")
          and contexto_recibido(d, "Le dan miedo o le molestan: las agujas")
          and contexto_recibido(d, "Acompañante/familia: su hija"))
    return ok, "contexto con memoria estructurada"


def _d2():
    # Cliente que vuelve: se le saluda por su nombre confirmado.
    hist = [
        {"fecha": "2026-11-17T10:00:00+00:00", "quien_hablo": "cliente",
         "mensaje": "¿cuánto cuesta la limpieza?"},
        {"fecha": "2026-11-17T10:01:00+00:00", "quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600."},
    ]
    d = nuevo_r(cliente=_cliente_base(nombre="María López"), historial=hist)
    msg(d, "hola, volví")
    ok = contexto_recibido(d, "El cliente se llama María López")
    return ok, "saludo a cliente que vuelve"


# ---------------------------------------------------------------------------
# E. G7: servicios con precios (guion + R14)
# ---------------------------------------------------------------------------

_SERVICIOS = [("Limpieza dental", "$600"), ("Revisión", "$200")]


def _e1():
    # El ejemplo del guion ya da servicios CON precios (no deflecta),
    # y la regla lo prohíbe explícitamente. Sincronizado en .md.
    g = agente_mod.guion()
    texto_md = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "guion-robot.md"), encoding="utf-8").read()
    ok = ("¿Cuál te interesa? Los más pedidos" not in g
          and "la limpieza ($600)" in g
          and "NUNCA respondas" in g
          and "¿Cuál te interesa? Los más pedidos" not in texto_md
          and "NUNCA respondas" in texto_md)
    return ok, "ejemplo y regla G7"


def _e2():
    # R14: deflexión sin precios → lista real desde el Conocimiento.
    texto, viols = revisar_respuesta(
        "¿Cuál te interesa? Los más pedidos son la limpieza, la revisión y el blanqueamiento.",
        {"ultimo_mensaje_cliente": "¿qué servicios tienen?",
         "ultimo_mensaje_robot": ""},
        "Jose Ramon",
        servicios_conocidos=_SERVICIOS,
    )
    ok = "R14" in viols and "$600" in texto and "$200" in texto
    return ok, f"viols={viols} texto={texto!r}"


def _e3():
    # R14 no toca respuestas que ya dan precio.
    texto, viols = revisar_respuesta(
        "La limpieza cuesta $600. ¿Cuál te interesa?",
        {"ultimo_mensaje_cliente": "¿qué servicios tienen?",
         "ultimo_mensaje_robot": ""},
        "Jose Ramon",
        servicios_conocidos=_SERVICIOS,
    )
    return "R14" not in viols, f"viols={viols}"


def _e4():
    # R14 no se aplica sin servicios conocidos (nunca inventa).
    texto, viols = revisar_respuesta(
        "¿Cuál te interesa? Los más pedidos son la limpieza.",
        {"ultimo_mensaje_cliente": "¿qué servicios tienen?",
         "ultimo_mensaje_robot": ""},
        "Jose Ramon",
    )
    return "R14" not in viols, f"viols={viols}"


def _e5():
    # R14 no se aplica si el cliente no preguntó por servicios.
    texto, viols = revisar_respuesta(
        "¿Cuál te interesa? Los más pedidos son la limpieza.",
        {"ultimo_mensaje_cliente": "¿a qué hora abren?",
         "ultimo_mensaje_robot": ""},
        "Jose Ramon",
        servicios_conocidos=_SERVICIOS,
    )
    return "R14" not in viols, f"viols={viols}"


def _e6():
    # servicios_de_conocimiento: solo tipo servicio con precio, máx 5.
    filas = [
        {"tipo": "servicio", "pregunta_o_servicio": "Limpieza",
         "respuesta_o_precio": "$600"},
        {"tipo": "faq", "pregunta_o_servicio": "Horario",
         "respuesta_o_precio": "$100"},
        {"tipo": "servicio", "pregunta_o_servicio": "Sin precio",
         "respuesta_o_precio": "a consultar"},
        {"tipo": "servicio", "pregunta_o_servicio": "Revisión",
         "respuesta_o_precio": "200 pesos"},
    ]
    serv = servicios_de_conocimiento(filas)
    ok = serv == [("Limpieza", "$600"), ("Revisión", "200 pesos")]
    return ok, f"serv={serv}"


def _e7():
    # R14 no toca una respuesta en prosa sin deflexión.
    texto, viols = revisar_respuesta(
        "Tenemos limpieza, revisión y blanqueamiento, todos con precios accesibles.",
        {"ultimo_mensaje_cliente": "¿qué servicios tienen?",
         "ultimo_mensaje_robot": ""},
        "Jose Ramon",
        servicios_conocidos=_SERVICIOS,
    )
    return "R14" not in viols, f"viols={viols}"


# ---------------------------------------------------------------------------
# F. G4 documentado (sin cambio de código)
# ---------------------------------------------------------------------------

def _f1():
    # G4 de la batería dorada: el robot contestó la pregunta y recordó
    # la propuesta en una frase. Eso es lo que el guion vigente manda
    # ("recuérdala en una frase corta", afirmado por test_v2_12): la
    # batería dorada es más estricta que el guion. No es un bug; se
    # documenta aquí y en el reporte. Este caso fija la decisión.
    # (El guion lo trae partido en dos líneas: se normaliza igual que
    # test_v2_12.)
    g = " ".join(agente_mod.guion().split())
    return "recuérdala en una frase corta" in g, "guion G4 (documentado)"


# ---------------------------------------------------------------------------
# G. G18 convertido de repro_g18.py: confirmar pide nombre y número
# ---------------------------------------------------------------------------

def _g1():
    d = nuevo_r(
        espejo=[{"Teléfono": TEL, "Estado": "Confirmada", "Fecha": "2026-11-25",
                 "Notas": "Paciente: Jose Ramon"}],
        propuesta=_propuesta())
    btn(d, "confirmar_cita")
    ok = any("¿me das tu nombre completo" in t for t in d.textos)
    return ok, f"textos={d.textos}"


# ---------------------------------------------------------------------------

def main():
    caso("A1 fusionar: el nombre confirmado manda", _a1)
    caso("A2 fusionar: nombre nuevo entra si no había", _a2)
    caso("A3 nombre confirmado se escribe en Clientes", _a3)
    caso("A4 contexto saluda con el nombre confirmado", _a4)
    caso("A5 regex captura 'me llamo X'", _a5)
    caso("A6 regex de nombre es conservador", _a6)
    caso("A7 estado prefiere el nombre de Clientes", _a7)
    caso("A8 actualizar_nombre_cliente escribe en B", _a8)
    caso("B1 número de registro se lee del espejo", _b1)
    caso("B2 confirmar no vuelve a pedir nombre/número conocidos", _b2)
    caso("B3 propuesta se prellena con el número conocido", _b3)
    caso("B4 número en texto libre queda en el espejo", _b4)
    caso("C1 regex de correo", _c1)
    caso("C2 RespuestaAgente trae correo", _c2)
    caso("C3 guardar_memoria_cliente escribe Z (con encabezado)", _c3)
    caso("C4 contexto incluye el correo", _c4)
    caso("C5 correo de la IA se guarda", _c5)
    caso("C6 guion de correo sincronizado", _c6)
    caso("D1 contexto con preferencias/miedos/acompañante", _d1)
    caso("D2 cliente que vuelve saludado por su nombre", _d2)
    caso("E1 ejemplo y regla G7 en el guion", _e1)
    caso("E2 R14 reemplaza deflexión por lista real", _e2)
    caso("E3 R14 no toca respuesta con precio", _e3)
    caso("E4 R14 sin servicios conocidos no se aplica", _e4)
    caso("E5 R14 sin pregunta de servicios no se aplica", _e5)
    caso("E6 servicios_de_conocimiento filtra bien", _e6)
    caso("E7 R14 no toca prosa sin deflexión", _e7)
    caso("F1 G4 documentado (guion manda el recordatorio breve)", _f1)
    caso("G1 G18: confirmar pide nombre y número", _g1)

    print()
    fallos = [n for n, ok in RESULTADOS if not ok]
    if fallos:
        print(f"recolección dinámica: {len(fallos)} FALLOS: {fallos}")
        sys.exit(1)
    print(f"recolección dinámica: todo verde ({len(RESULTADOS)} casos)")


if __name__ == "__main__":
    main()
