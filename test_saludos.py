"""Pruebas del saludo aprovechado (v3.22.0): menú de botones + ficha mínima.

Lo que Jose pidió el 2026-11-26:
- Quien solo saluda también queda registrado en Clientes (estatus
  "saludo"), para aprovechar cada entrada de mensajes como base.
- El saludo trae un menú de botones (ver servicios / agendar cita /
  hablar con persona) que reduce fricción; un toque vale como si lo
  hubiera escrito y la IA compone la respuesta.
- El reporte cuenta cuántos "saludaron y no agendaron" (demanda que
  llegó y no se convirtió).

Uso:  python3 test_saludos.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
Sin internet: todo con fakes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import robot.logic as logic_mod  # noqa: E402
import robot.report as report_mod  # noqa: E402
import robot.sheets as sheets_mod  # noqa: E402
from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import (  # noqa: E402
    Dependencias,
    atender_boton,
    atender_mensaje,
    contar_semana,
)

RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not condicion else ""))


class _MP:
    """Parche mínimo con restauración (sin pytest)."""

    def __init__(self):
        self._orig = []

    def set(self, obj, nombre, valor):
        self._orig.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)

    def restore(self):
        for obj, nombre, valor in reversed(self._orig):
            setattr(obj, nombre, valor)
        self._orig.clear()


class _DTFija(datetime):
    """datetime con now() fijo, para ventanas deterministas."""

    _ahora = datetime.fromisoformat("2026-12-15T10:00:00-07:00")

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls._ahora.astimezone(tz)
        return cls._ahora.replace(tzinfo=None)


CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]

# Lunes 2026-11-23 10:00 Mazatlán (clínica abierta).
AHORA = datetime(2026, 11, 23, 17, 0, tzinfo=timezone.utc)
# Domingo 2026-11-15 20:00 Mazatlán (clínica cerrada).
NOCHE = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
# Para la propuesta de cita (mismo patrón que test_v3_11).
DOMINGO = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
LUNES = "2026-11-23T09:00:00-07:00"
MARTES = "2026-11-24T09:00:00-07:00"
MIERCOLES = "2026-11-25T09:00:00-07:00"
FUTURA = "2026-11-24T09:00:00-07:00"


class DepsSaludos(Dependencias):
    """Servicios de mentira con botones capturados e historial real."""

    def __init__(self, agente_cola=None, cliente=None, huecos=None,
                 botones_fallan=False):
        self.agente_cola = list(agente_cola or [])
        self.textos = []
        self.botones = []  # (telefono, texto, botones)
        self.conversaciones = []
        self.clientes = []
        self.citas = []
        self.diagnosticos = []
        self.cliente = cliente
        self.huecos = huecos if huecos is not None else [LUNES, MARTES, MIERCOLES]
        self.botones_fallan = botones_fallan
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
        return [c for c in self.conversaciones if c["telefono"] == telefono]

    def leer_propuestas(self):
        return []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.ultimo_mensaje_agente = mensaje
        if self.agente_cola:
            return self.agente_cola.pop(0)
        return RespuestaAgente(respuesta_texto="¡Hola! ¿En qué te puedo ayudar?")

    def enviar_texto(self, telefono, texto):
        self.textos.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def enviar_botones(self, telefono, texto, botones):
        if self.botones_fallan:
            raise Exception("WhatsApp devolvió 400: prueba simulada")
        self.botones.append((telefono, texto, list(botones)))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({
            "fecha": fecha, "telefono": telefono, "quien_hablo": quien,
            "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo,
        })

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="",
                          origen="whatsapp", estatus="en conversacion", handoff="no"):
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita,
                              "origen": origen, "estatus": estatus, "handoff": handoff})

    def registrar_diagnostico(self, fecha, componente, estado, detalle, telefono="", contexto=""):
        self.diagnosticos.append({"componente": componente, "estado": estado,
                                  "detalle": detalle, "telefono": telefono,
                                  "contexto": contexto})

    def guardar_memoria_cliente(self, telefono, resumen="", interes="",
                                proxima_accion="", preferencias="", miedos=""):
        pass

    def guardar_propuesta(self, telefono, propuesta):
        pass

    def borrar_propuesta(self, telefono):
        pass

    def proximos_huecos_libres(self, conocimiento, ahora):
        return list(self.huecos)

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
        pass

    def actualizar_cita_espejo(self, telefono, fecha_cita, estado=None, notas=None):
        pass

    def leer_citas_espejo(self):
        return []

    def actualizar_notas_cita(self, telefono, fecha_cita, notas):
        pass

    def alerta_cita_confirmada(self, nombre, telefono, motivo, fecha_bonita, fecha):
        pass

    def alerta_lead_caliente(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        pass

    def alerta_handoff(self, nombre, telefono, motivo, mensaje, fecha, resumen="", hilo=""):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass

    def cancelar_cita(self, telefono, fecha_cita):
        return True

    def cancelar_cita_cliente(self, telefono):
        pass


def _limpiar():
    logic_mod._CITAS_PENDIENTES.clear()
    logic_mod._RETOMAR.clear()


def _ids_menu(d):
    return [b for _, _, botones in d.botones for (b, _t) in botones]


# ---------------------------------------------------------------------------
# A. Ficha mínima
# ---------------------------------------------------------------------------

def a1():
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000001", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    ok = (len(d.clientes) == 1 and d.clientes[0]["estatus"] == "saludo"
          and d.clientes[0]["telefono"] == "6670000001"
          and d.clientes[0]["motivo"] == "Hola")
    return ok, f"clientes={d.clientes}"


def a2():
    _limpiar()
    agente = RespuestaAgente(respuesta_texto="Hola Ana, ¿en qué te ayudo?",
                             nombre="Ana", motivo="Limpieza dental")
    d = DepsSaludos(agente_cola=[agente])
    atender_mensaje(d, "6670000002", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    ok = (len(d.clientes) == 1 and d.clientes[0]["estatus"] == "calificado"
          and d.clientes[0]["motivo"] == "Limpieza dental")
    return ok, f"clientes={d.clientes}"


def a3():
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000003", "Ana", "Hola", con_ritmo=False, ahora=NOCHE)
    ok = (len(d.clientes) == 1 and d.clientes[0]["estatus"] == "en conversacion")
    return ok, f"clientes={d.clientes}"


def a4():
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000004", "Ana", "ok gracias", con_ritmo=False, ahora=AHORA)
    ok = len(d.clientes) == 0
    return ok, f"clientes={d.clientes}"


# ---------------------------------------------------------------------------
# B. Menú de botones en el saludo
# ---------------------------------------------------------------------------

def b1():
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000011", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    ids = _ids_menu(d)
    ok = (ids == ["menu_servicios", "menu_cita", "hablar_persona"]
          and any("ayudar" in t for _, t in d.textos))
    return ok, f"botones={d.botones} textos={d.textos}"


def b2():
    _limpiar()
    agente = RespuestaAgente(respuesta_texto="La limpieza cuesta $600.")
    d = DepsSaludos(agente_cola=[agente])
    atender_mensaje(d, "6670000012", "Ana", "hola, ¿cuánto cuesta la limpieza?",
                    con_ritmo=False, ahora=AHORA)
    ok = len(d.botones) == 0 and len(d.textos) == 1
    return ok, f"botones={d.botones} textos={d.textos}"


def b3():
    _limpiar()
    cliente = {"nombre": "Ana", "telefono": "6670000013", "motivo": "Limpieza dental",
               "fecha_cita": FUTURA, "estatus": "agendado", "handoff": "no"}
    d = DepsSaludos(cliente=cliente)
    atender_mensaje(d, "6670000013", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    ok = len(d.botones) == 0 and len(d.textos) == 1
    return ok, f"botones={d.botones} textos={d.textos}"


def b4():
    _limpiar()
    agente = RespuestaAgente(respuesta_texto="Te paso con una persona del equipo.",
                             necesita_handoff="si", motivo_handoff="pide persona")
    d = DepsSaludos(agente_cola=[agente])
    r = atender_mensaje(d, "6670000014", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    ok = r.get("handoff") is True and len(d.botones) == 0
    return ok, f"r={r} botones={d.botones}"


def b5():
    _limpiar()
    d = DepsSaludos(botones_fallan=True)
    try:
        atender_mensaje(d, "6670000015", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
        sin_crash = True
    except Exception as exc:  # noqa: BLE001
        sin_crash = False
        return False, f"excepción {exc}"
    fallos = [x for x in d.diagnosticos if x["contexto"] == "menu saludo"]
    ok = (sin_crash and len(fallos) == 1
          and any("ayudar" in t for _, t in d.textos))
    return ok, f"diagnosticos={d.diagnosticos} textos={d.textos}"


# ---------------------------------------------------------------------------
# C. Toque de botón del menú
# ---------------------------------------------------------------------------

def c1():
    _limpiar()
    agente = RespuestaAgente(
        respuesta_texto="Tenemos limpieza dental, blanqueamiento y revisión.")
    d = DepsSaludos(agente_cola=[agente])
    r = atender_boton(d, "6670000021", "Ana", "menu_servicios",
                      con_ritmo=False, ahora=AHORA)
    ok = (r.get("respondio") is True
          and "¿Qué servicios tienen?" in d.ultimo_mensaje_agente
          and any("blanqueamiento" in t for _, t in d.textos))
    return ok, f"r={r} textos={d.textos} ultimo={d.ultimo_mensaje_agente[:80]!r}"


def c2():
    _limpiar()
    agente = RespuestaAgente(respuesta_texto="Perfecto, te agendo.",
                             quiere_agendar="si", fecha_cita=MARTES,
                             motivo="limpieza")
    d = DepsSaludos(agente_cola=[agente])
    r = atender_boton(d, "6670000022", "Ana", "menu_cita",
                      con_ritmo=False, ahora=DOMINGO)
    ids = _ids_menu(d)
    ok = (r.get("cita_propuesta") is True
          and "confirmar_cita" in ids
          and "Quiero agendar una cita" in d.ultimo_mensaje_agente)
    _limpiar()
    return ok, f"r={r} botones={d.botones}"


# ---------------------------------------------------------------------------
# D. Fusión, conteos y reporte
# ---------------------------------------------------------------------------

def _fila_cliente(estatus, motivo="Hola", fecha="2026-11-23T10:00:00-07:00"):
    return {"fecha": fecha, "nombre": "", "telefono": "6670000099",
            "motivo": motivo, "fecha_cita": "", "origen": "whatsapp",
            "estatus": estatus, "handoff": "no"}


def d1():
    viejo = _fila_cliente("saludo")
    nuevo = _fila_cliente("calificado", motivo="Limpieza dental")
    fusionada = sheets_mod.fusionar_cliente(viejo, nuevo)
    # Columna G (índice 6) es estatus.
    ok = fusionada[6] == "calificado" and fusionada[3] == "Limpieza dental"
    return ok, f"fusionada={fusionada}"


def d2():
    viejo = _fila_cliente("calificado", motivo="Limpieza dental")
    nuevo = _fila_cliente("saludo")
    fusionada = sheets_mod.fusionar_cliente(viejo, nuevo)
    ok = fusionada[6] == "calificado" and fusionada[3] == "Limpieza dental"
    return ok, f"fusionada={fusionada}"


def d3():
    desde = datetime.fromisoformat("2026-11-22T00:00:00-07:00")
    hasta = datetime.fromisoformat("2026-11-24T00:00:00-07:00")
    clientes = [
        _fila_cliente("saludo", fecha="2026-11-23T10:00:00-07:00"),
        {**_fila_cliente("calificado", motivo="Limpieza dental"),
         "telefono": "6670000100", "fecha": "2026-11-23T11:00:00-07:00"},
        {**_fila_cliente("agendado", motivo="Limpieza dental"),
         "telefono": "6670000101", "fecha": "2026-11-23T12:00:00-07:00"},
    ]
    conteo = contar_semana([], clientes, desde, hasta)
    ok = conteo["clientes_calificados"] == 2 and conteo["citas_agendadas"] == 1
    return ok, f"conteo={conteo}"


def d4():
    mp = _MP()
    try:
        conversaciones = [
            {"fecha": "2026-12-10T10:00:00-07:00", "telefono": "201",
             "quien_hablo": "cliente", "mensaje": "hola", "robot_respondio": "si",
             "motivo": "Limpieza dental"},
            {"fecha": "2026-12-10T10:01:00-07:00", "telefono": "201",
             "quien_hablo": "robot", "mensaje": "¡Hola!", "robot_respondio": "si",
             "motivo": "Limpieza dental"},
        ]
        clientes = [
            {"fecha": "2026-12-10T10:00:00-07:00", "nombre": "", "telefono": "201",
             "motivo": "hola", "fecha_cita": "", "estatus": "saludo", "handoff": "no"},
            {"fecha": "2026-12-10T11:00:00-07:00", "nombre": "", "telefono": "202",
             "motivo": "buenas", "fecha_cita": "", "estatus": "saludo", "handoff": "no"},
            {"fecha": "2026-12-10T12:00:00-07:00", "nombre": "Ana", "telefono": "203",
             "motivo": "Limpieza dental", "fecha_cita": "2026-12-20T10:00:00-07:00",
             "estatus": "agendado", "handoff": "no"},
            # Fuera de la ventana: no debe contar.
            {"fecha": "2026-11-20T10:00:00-07:00", "nombre": "", "telefono": "204",
             "motivo": "hola", "fecha_cita": "", "estatus": "saludo", "handoff": "no"},
        ]
        capturado = {}

        def leer_fake(pestana, spreadsheet_id=None):
            return {"Conversaciones": conversaciones, "Clientes": clientes,
                    "Citas": [], "Conocimiento": [], "Reporte": []}.get(pestana, [])

        def enviar_fake(dest, asunto, cuerpo, html=None):
            capturado.update(dest=dest, asunto=asunto, cuerpo=cuerpo, html=html)

        mp.set(report_mod, "datetime", _DTFija)
        mp.set(report_mod, "leer_pestana", leer_fake)
        mp.set(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
        mp.set(report_mod, "enviar_correo", enviar_fake)
        mp.set(report_mod, "guardar_reporte", lambda *a, **k: None)
        mp.set(report_mod, "funcion_activa", lambda n: True)
        mp.set(report_mod, "nombre_negocio", lambda: "Clínica de prueba")
        mp.set(report_mod, "correo_dueno", lambda: "dueno@ejemplo.com")

        resultado = report_mod.generar_reporte_semanal()
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (resultado.get("saludaron_sin_agendar") == 2
              and "Saludaron y no agendaron: 2" in cuerpo
              and "Saludaron y no agendaron" in html)
        return ok, f"res={resultado.get('saludaron_sin_agendar')} cuerpo_ok={'Saludaron y no agendaron: 2' in cuerpo} html_ok={'Saludaron y no agendaron' in html}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# E. Adversariales: variantes de saludo
# ---------------------------------------------------------------------------

def e1():
    # Saludo con acento y mayúsculas: también es saludo.
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000031", "Ana", "Buenas Tardes", con_ritmo=False, ahora=AHORA)
    ok = (len(d.clientes) == 1 and d.clientes[0]["estatus"] == "saludo"
          and len(d.botones) == 1)
    return ok, f"clientes={d.clientes} botones={d.botones}"


def e2():
    # "hola quiero agendar" NO es solo saludo: no hay menú, va la cita.
    _limpiar()
    agente = RespuestaAgente(respuesta_texto="Perfecto, te agendo.",
                             quiere_agendar="si", fecha_cita=MARTES,
                             motivo="limpieza")
    d = DepsSaludos(agente_cola=[agente])
    r = atender_mensaje(d, "6670000032", "Ana", "hola quiero agendar",
                        con_ritmo=False, ahora=DOMINGO)
    ok = r.get("cita_propuesta") is True and "menu_servicios" not in _ids_menu(d)
    _limpiar()
    return ok, f"r={r} botones={d.botones}"


def e3():
    # Doble saludo: el segundo también recibe menú (reenganche), sin romper.
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000033", "Ana", "Hola", con_ritmo=False, ahora=AHORA)
    atender_mensaje(d, "6670000033", "Ana", "hola", con_ritmo=False, ahora=AHORA)
    ok = len(d.botones) == 2 and len(d.textos) == 2
    return ok, f"botones={len(d.botones)} textos={len(d.textos)}"


def e4():
    # Saludo de noche: registra "en conversacion" (regla vieja) y el
    # menú también sale (el robot atiende 24/7).
    _limpiar()
    d = DepsSaludos()
    atender_mensaje(d, "6670000034", "Ana", "Buenas noches", con_ritmo=False, ahora=NOCHE)
    ok = (len(d.clientes) == 1 and d.clientes[0]["estatus"] == "en conversacion"
          and len(d.botones) == 1)
    return ok, f"clientes={d.clientes} botones={len(d.botones)}"


def main():
    casos = [
        ("A1 Saludo de día: ficha mínima con estatus saludo", a1),
        ("A2 Saludo con nombre/motivo: calificado (regla vieja)", a2),
        ("A3 Saludo de noche: en conversacion (regla vieja)", a3),
        ("A4 'ok gracias' de día: sin registro (regla vieja)", a4),
        ("B1 Saludo de día: menú de botones tras el saludo", b1),
        ("B2 Saludo con pregunta: sin menú", b2),
        ("B3 Saludo con cita vigente: sin menú", b3),
        ("B4 Saludo con handoff: sin menú", b4),
        ("B5 Botones fallan: saludo igual sale, se registra", b5),
        ("C1 Toque 'Ver servicios': la IA responde con servicios", c1),
        ("C2 Toque 'Agendar cita': propuesta con botones", c2),
        ("D1 Fusión: saludo sube a calificado", d1),
        ("D2 Fusión: calificado nunca baja a saludo", d2),
        ("D3 contar_semana: saludo no cuenta como calificado", d3),
        ("D4 Reporte: saludaron sin agendar en cuerpo, HTML y retorno", d4),
        ("E1 'Buenas Tardes': saludo con menú", e1),
        ("E2 'hola quiero agendar': no es solo saludo", e2),
        ("E3 Doble saludo: menú dos veces, sin romper", e3),
        ("E4 Saludo de noche: en conversacion + menú", e4),
    ]
    fallos = 0
    for nombre, fn in casos:
        try:
            ok, detalle = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
        if not ok:
            fallos += 1
        caso(nombre, ok, detalle)
    total = len(casos)
    print(f"\n{total - fallos}/{total} casos OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
