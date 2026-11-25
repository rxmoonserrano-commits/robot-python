"""Pruebas del registro del número en la Cloud API (v3.20.12).

Un número agregado en WhatsApp Manager queda 'Pendiente' y Meta no
entrega mensajes al webhook hasta registrarlo por API
(POST /{id}/register). La salud al arrancar consulta el estado del
número y, si no está conectado, intenta registrarlo. Todo es
best-effort: nunca rompe el arranque y todo queda en Diagnóstico.

Sin internet: todo con fakes, como las demás pruebas. No se toca
ninguna clave real.
"""

import sys

import robot.salud as salud_mod
import robot.whatsapp as wa_mod
from robot.config import settings

TOTAL = [0]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    TOTAL[0] += 1
    if condicion:
        print(f"[PASS] {nombre}")
    else:
        print(f"[FAIL] {nombre} — {detalle}")
        FALLOS.append(nombre)


# ---------- Fakes HTTP para robot/whatsapp.py ----------

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = "{}" if status == 200 else "error de Meta"

    def json(self):
        return self._payload


class _RequestsFalso:
    """Fake de requests para robot.whatsapp: graba llamadas y responde según guion."""

    def __init__(self, get_respuesta=None, post_respuesta=None):
        self.get_respuesta = get_respuesta or _Resp(200, {"status": "Connected"})
        self.post_respuesta = post_respuesta or _Resp(200, {"success": True})
        self.llamadas = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.llamadas.append(("GET", url, params))
        return self.get_respuesta

    def post(self, url, headers=None, json=None, timeout=None):
        self.llamadas.append(("POST", url, json))
        return self.post_respuesta


def _con_wa_falso(fake):
    orig = wa_mod.requests
    orig_id = settings.whatsapp_phone_number_id
    wa_mod.requests = fake
    settings.whatsapp_phone_number_id = "1407658669107360"
    return orig, orig_id


def _restaurar_wa(orig, orig_id):
    wa_mod.requests = orig
    settings.whatsapp_phone_number_id = orig_id


# ---------- consultar_estado_numero ----------

fake = _RequestsFalso(get_respuesta=_Resp(200, {
    "status": "Connected",
    "display_phone_number": "+52 669 100 1402",
    "verified_name": "Clínica Dental Sonrisa",
    "code_verification_status": "VERIFIED",
}))
orig, orig_id = _con_wa_falso(fake)
try:
    estado = wa_mod.consultar_estado_numero()
    metodo, url, params = fake.llamadas[0]
    caso("(a) consultar_estado: GET al número con los campos de estado",
         metodo == "GET"
         and url.endswith("/1407658669107360")
         and "status" in params.get("fields", "")
         and "code_verification_status" in params.get("fields", ""),
         f"llamada={fake.llamadas[0]}")
    caso("(a) consultar_estado: devuelve el JSON de Meta",
         estado.get("status") == "Connected"
         and estado.get("verified_name") == "Clínica Dental Sonrisa",
         f"estado={estado}")
finally:
    _restaurar_wa(orig, orig_id)

fake = _RequestsFalso(get_respuesta=_Resp(401))
orig, orig_id = _con_wa_falso(fake)
try:
    try:
        wa_mod.consultar_estado_numero()
        caso("(a) consultar_estado con 401 lanza WhatsAppError", False, "no lanzó")
    except wa_mod.WhatsAppError:
        caso("(a) consultar_estado con 401 lanza WhatsAppError", True)
finally:
    _restaurar_wa(orig, orig_id)

# ---------- registrar_numero ----------

fake = _RequestsFalso(post_respuesta=_Resp(200, {"success": True}))
orig, orig_id = _con_wa_falso(fake)
try:
    wa_mod.registrar_numero()
    metodo, url, cuerpo = fake.llamadas[0]
    caso("(b) registrar sin pin: POST a /register con messaging_product",
         metodo == "POST"
         and url.endswith("/1407658669107360/register")
         and cuerpo.get("messaging_product") == "whatsapp"
         and "pin" not in cuerpo,
         f"llamada={fake.llamadas[0]}")
finally:
    _restaurar_wa(orig, orig_id)

fake = _RequestsFalso(post_respuesta=_Resp(200, {"success": True}))
orig, orig_id = _con_wa_falso(fake)
try:
    wa_mod.registrar_numero(pin="123456")
    metodo, url, cuerpo = fake.llamadas[0]
    caso("(b) registrar con pin: el pin va en el cuerpo",
         cuerpo.get("pin") == "123456",
         f"cuerpo={cuerpo}")
finally:
    _restaurar_wa(orig, orig_id)

fake = _RequestsFalso(post_respuesta=_Resp(400))
orig, orig_id = _con_wa_falso(fake)
try:
    try:
        wa_mod.registrar_numero()
        caso("(b) registrar con error de Meta lanza WhatsAppError", False, "no lanzó")
    except wa_mod.WhatsAppError:
        caso("(b) registrar con error de Meta lanza WhatsAppError", True)
finally:
    _restaurar_wa(orig, orig_id)

# ---------- Integración en la salud al arrancar ----------

class DepsSalud:
    def __init__(self):
        self.diagnostico = []

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        self.diagnostico.append((componente, estado, detalle))


def _salud_con(estado=None, registrar_ok=True, estado_falla=False, pin="123456"):
    d = DepsSalud()
    orig_gemini = salud_mod.gemini.generar_texto
    orig_sheets = salud_mod.sheets.leer_control
    orig_booking = salud_mod.booking.hora_libre
    orig_requests = salud_mod.requests
    orig_consultar = wa_mod.consultar_estado_numero
    orig_registrar = wa_mod.registrar_numero
    orig_pin = settings.whatsapp_register_pin
    llamadas = {"registrar": 0, "pin": None}

    def texto_falso(prompt, json_mode=True):
        return "OK"

    def control_falso():
        return {"bot_activo": "SI"}

    def libre_falso(fecha_iso):
        return True

    class _RespSalud:
        status_code = 200
        text = "{}"

    class _RequestsSalud:
        def get(self, url, headers=None, timeout=None):
            return _RespSalud()

    def consultar_falso():
        if estado_falla:
            raise RuntimeError("sin red")
        return estado or {"status": "Connected",
                          "code_verification_status": "VERIFIED",
                          "verified_name": "Clínica Dental Sonrisa"}

    def registrar_falso(pin=""):
        llamadas["registrar"] += 1
        llamadas["pin"] = pin
        if not registrar_ok:
            raise RuntimeError("WhatsApp devolvió 400: ya registrado")
        return {"success": True}

    salud_mod.gemini.generar_texto = texto_falso
    salud_mod.sheets.leer_control = control_falso
    salud_mod.booking.hora_libre = libre_falso
    salud_mod.requests = _RequestsSalud()
    wa_mod.consultar_estado_numero = consultar_falso
    wa_mod.registrar_numero = registrar_falso
    settings.whatsapp_register_pin = pin
    try:
        res = salud_mod.revisar_salud(d)
        return d, res, llamadas
    finally:
        salud_mod.gemini.generar_texto = orig_gemini
        salud_mod.sheets.leer_control = orig_sheets
        salud_mod.booking.hora_libre = orig_booking
        salud_mod.requests = orig_requests
        wa_mod.consultar_estado_numero = orig_consultar
        wa_mod.registrar_numero = orig_registrar
        settings.whatsapp_register_pin = orig_pin


d, res, llamadas = _salud_con()
estados = {r["componente"]: r["estado"] for r in res}
caso("(c) Número conectado: registro_numero OK y NO intenta registrar",
     estados.get("registro_numero") == "OK"
     and llamadas["registrar"] == 0,
     f"estados={estados}, llamadas={llamadas}")

d, res, llamadas = _salud_con(
    estado={"status": "Pending", "code_verification_status": "VERIFIED",
            "verified_name": ""})
estados = {r["componente"]: r["estado"] for r in res}
caso("(c) Número pendiente: registra y queda OK, con el pin de configuración",
     estados.get("registro_numero") == "OK"
     and llamadas["registrar"] == 1
     and llamadas["pin"] == "123456",
     f"estados={estados}, llamadas={llamadas}")

d, res, llamadas = _salud_con(
    estado={"status": "Pending", "code_verification_status": "UNVERIFIED"},
    registrar_ok=False)
estados = {r["componente"]: r["estado"] for r in res}
caso("(c) Registro fallido: registro_numero AVISO y la salud no rompe",
     estados.get("registro_numero") == "AVISO"
     and estados.get("gemini") == "OK"
     and estados.get("whatsapp") == "OK",
     f"estados={estados}")

d, res, llamadas = _salud_con(estado_falla=True)
estados = {r["componente"]: r["estado"] for r in res}
caso("(c) Consulta de estado fallida: registro_numero AVISO y la salud no rompe",
     estados.get("registro_numero") == "AVISO"
     and estados.get("gemini") == "OK"
     and llamadas["registrar"] == 0,
     f"estados={estados}")

d, res, llamadas = _salud_con(
    estado={"status": "Pending", "code_verification_status": "VERIFIED"},
    pin="")
caso("(c) Sin pin configurado: registra sin pin (cadena vacía)",
     llamadas["registrar"] == 1 and llamadas["pin"] == "",
     f"llamadas={llamadas}")

print()
if FALLOS:
    print(f"{len(FALLOS)} de {TOTAL[0]} casos fallaron: {FALLOS}")
    sys.exit(1)
print(f"Todos los casos pasaron ({TOTAL[0]}).")
