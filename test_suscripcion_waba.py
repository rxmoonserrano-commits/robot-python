"""Prueba permanente v3.20.13: suscripción de la app a la cuenta de WhatsApp.

Sin la suscripción (POST /{waba}/subscribed_apps), Meta no reenvía al webhook
los mensajes de los números que viven en esa cuenta, aunque estén registrados
por API. El robot la hace al arrancar y lo deja en Diagnóstico como
'suscripcion_waba'. Best-effort: nunca rompe el arranque.

Uso: python3 test_suscripcion_waba.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pasadas = 0
fallidas = 0


def caso(nombre, cond, detalle=""):
    global pasadas, fallidas
    if cond:
        pasadas += 1
        print(f"  OK  {nombre}")
    else:
        fallidas += 1
        print(f"FALLO {nombre} {detalle}")


class _Resp:
    def __init__(self, status, payload=None, texto=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = texto or str(self._payload)

    def json(self):
        return self._payload


# ---------- 1. suscribir_waba: URL, header y errores ----------

from robot import whatsapp as wa_mod  # noqa: E402

llamadas = []


class _ReqFalso:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload or {"success": True}

    def post(self, url, headers=None, json=None, timeout=None):
        llamadas.append({"url": url, "headers": headers, "json": json})
        return _Resp(self.status, self.payload)

    def get(self, url, headers=None, params=None, timeout=None):
        llamadas.append({"url": url, "headers": headers, "params": params})
        return _Resp(self.status, self.payload)


orig_req = wa_mod.requests
try:
    wa_mod.requests = _ReqFalso(200)
    llamadas.clear()
    r = wa_mod.suscribir_waba("123456789")
    caso("(a) suscribir_waba OK devuelve el JSON de Meta",
         r.get("success") is True)
    caso("(b) POST a /{waba}/subscribed_apps",
         llamadas and llamadas[0]["url"].endswith("/123456789/subscribed_apps"),
         f"llamadas={llamadas}")
    caso("(c) lleva el header de autorización",
         llamadas and "Authorization" in (llamadas[0]["headers"] or {}))

    wa_mod.requests = _ReqFalso(400, {"error": {"message": "bad"}})
    try:
        wa_mod.suscribir_waba("123456789")
        caso("(d) error 400 lanza WhatsAppError", False)
    except wa_mod.WhatsAppError:
        caso("(d) error 400 lanza WhatsAppError", True)

    class _ReqExplota:
        def post(self, *a, **k):
            raise ConnectionError("sin red")

    wa_mod.requests = _ReqExplota()
    try:
        wa_mod.suscribir_waba("123456789")
        caso("(e) fallo de red se propaga como excepción capturable", False)
    except ConnectionError:
        caso("(e) fallo de red se propaga como excepción capturable", True)
finally:
    wa_mod.requests = orig_req

# ---------- 2. Integración con salud: los 3 caminos ----------

from robot import salud as salud_mod  # noqa: E402
from robot.config import settings  # noqa: E402


class _Deps:
    def __init__(self):
        self.diagnostico = []

    def registrar_diagnostico(self, fecha, componente, estado, detalle, **k):
        self.diagnostico.append(
            {"componente": componente, "estado": estado, "detalle": detalle})


def _componente_suscripcion(waba_id, status_post=200):
    """Corre revisar_salud con fakes y devuelve (estado, detalle) de suscripcion_waba."""
    d = _Deps()
    orig_waba = settings.whatsapp_waba_id
    orig_wa_req = wa_mod.requests
    orig_gemini = salud_mod.gemini.generar_texto
    orig_sheets = salud_mod.sheets.leer_control
    orig_booking = salud_mod.booking.hora_libre
    orig_requests = salud_mod.requests

    class _WaReq:
        def get(self, url, headers=None, params=None, timeout=None):
            return _Resp(200, {"status": "Connected",
                               "code_verification_status": "VERIFIED",
                               "verified_name": "Negocio Demo"})

        def post(self, url, headers=None, json=None, timeout=None):
            return _Resp(status_post, {"success": True} if status_post == 200
                         else {"error": {"message": "no"}})

    try:
        settings.whatsapp_waba_id = waba_id
        wa_mod.requests = _WaReq()
        salud_mod.gemini.generar_texto = lambda *a, **k: "ok"
        salud_mod.sheets.leer_control = lambda *a, **k: {}
        salud_mod.booking.hora_libre = lambda *a, **k: True
        salud_mod.requests = type("R", (), {
            "get": staticmethod(lambda *a, **k: _Resp(200))})()
        res = salud_mod.revisar_salud(d)
    finally:
        settings.whatsapp_waba_id = orig_waba
        wa_mod.requests = orig_wa_req
        salud_mod.gemini.generar_texto = orig_gemini
        salud_mod.sheets.leer_control = orig_sheets
        salud_mod.booking.hora_libre = orig_booking
        salud_mod.requests = orig_requests

    for r in res:
        if r["componente"] == "suscripcion_waba":
            return r["estado"], r["detalle"]
    return None, ""


estado, detalle = _componente_suscripcion("987654321", 200)
caso("(f) con WABA ID y Meta OK → suscripcion_waba OK",
     estado == "OK" and "987654321" in detalle, f"{estado} {detalle}")

estado, detalle = _componente_suscripcion("987654321", 400)
caso("(g) con WABA ID y Meta 400 → AVISO sin romper",
     estado == "AVISO" and "falló" in detalle, f"{estado} {detalle}")

estado, detalle = _componente_suscripcion("", 200)
caso("(h) sin WABA ID → AVISO que pide configurarla",
     estado == "AVISO" and "WHATSAPP_WABA_ID" in detalle, f"{estado} {detalle}")

print(f"\n{pasadas} OK, {fallidas} fallidas")
sys.exit(1 if fallidas else 0)
