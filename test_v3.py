"""Pruebas de la v3.0 (el producto): lo que la revisión encontró crudo.

(a) El reporte semanal vuelve a ser prosa (el JSON obligatorio de la
    v2.13 lo rompió): generar_texto en modo texto NO pide JSON a la API.
(b) Seguridad: la clave de dueño y la firma de Meta.
(c) Perfil del negocio: el robot deja de decir "la clínica" a mano;
    el nombre, el giro y la recepcionista salen de la configuración.
(d) Salud al arrancar: cada pieza se revisa y queda en Diagnóstico.
(e) Sheets con caché: Clientes se lee una vez por mensaje, no tres.
(f) Buzón persistente: un reinicio ya no pierde los lotes pendientes.
(g) Archivos vigentes: versión 3.0.0, .env.example con modelos vivos,
    instalador sin textos viejos.

Sin internet: todo con fakes, como las demás pruebas. No se toca
ninguna clave real.
"""

import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone

import robot.agent as agent_mod
import robot.gemini as gemini_mod
import robot.negocio as negocio_mod
import robot.report as report_mod
import robot.revision as revision_mod
import robot.salud as salud_mod
import robot.sheets as sheets_mod
from robot.agrupar import Agrupador
from robot.config import settings
from robot.seguridad import token_admin_ok, verificar_firma_meta

TOTAL = [0]
FALLOS = []


def caso(nombre, condicion, detalle=""):
    TOTAL[0] += 1
    if condicion:
        print(f"[PASS] {nombre}")
    else:
        print(f"[FAIL] {nombre} — {detalle}")
        FALLOS.append(nombre)


# ---------- (a) Reporte en texto plano ----------

class _RespFalsa:
    def __init__(self, status_code=200, texto=""):
        self.status_code = status_code
        self._texto = texto

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._texto}]}}]}


def _probar_generar_texto():
    import robot.gemini as g

    capturados = []
    original_post = g.requests.post
    original_key = g.settings.gemini_api_key
    original_ultimo = g._ULTIMO_MODELO_OK
    g.settings.gemini_api_key = "clave-falsa"
    g._ULTIMO_MODELO_OK = ""

    def post_falso(url, json=None, timeout=None):
        capturados.append(json)
        return _RespFalsa(200, "Hola, soy prosa.")

    g.requests.post = post_falso
    try:
        texto_json = g.generar_texto("dame un JSON", json_mode=True)
        texto_plano = g.generar_texto("dame prosa", json_mode=False)
    finally:
        g.requests.post = original_post
        g.settings.gemini_api_key = original_key
        g._ULTIMO_MODELO_OK = original_ultimo
    return capturados, texto_json, texto_plano


capturados, texto_json, texto_plano = _probar_generar_texto()
caso("(a) En modo JSON, la API pide JSON con temperatura 0.3",
     capturados and capturados[0]["generationConfig"].get("response_mime_type") == "application/json"
     and capturados[0]["generationConfig"].get("temperature") == 0.3
     and texto_json == "Hola, soy prosa.",
     f"payload={capturados[0] if capturados else None}")
caso("(a) En modo texto, la API NO pide JSON (el reporte es prosa)",
     len(capturados) == 2
     and "response_mime_type" not in capturados[1]["generationConfig"]
     and texto_plano == "Hola, soy prosa.",
     f"payload={capturados[1] if len(capturados) > 1 else None}")


def _probar_reporte():
    ahora = datetime.now(timezone.utc)
    fecha = ahora.isoformat()
    conv = [
        {"fecha": fecha, "telefono": "521", "quien_hablo": "cliente",
         "mensaje": "hola", "robot_respondio": "si", "motivo": ""},
        {"fecha": fecha, "telefono": "521", "quien_hablo": "robot",
         "mensaje": "hola", "robot_respondio": "si", "motivo": ""},
    ]
    cli = [{"fecha": fecha, "nombre": "Jose", "telefono": "521",
            "motivo": "limpieza", "fecha_cita": "", "origen": "whatsapp",
            "estatus": "agendado", "handoff": "no"}]
    correos = []
    guardados = []
    orig_leer = report_mod.leer_pestana
    orig_texto = report_mod.generar_texto
    orig_correo = report_mod.enviar_correo
    orig_guardar = report_mod.guardar_reporte
    report_mod.leer_pestana = lambda tab: conv if tab == "Conversaciones" else cli
    report_mod.generar_texto = lambda prompt, json_mode=True: "Esta semana atendimos bien."
    report_mod.enviar_correo = lambda dest, asunto, cuerpo, html=None: correos.append((dest, asunto, cuerpo))
    report_mod.guardar_reporte = lambda *args: guardados.append(args)
    try:
        resultado = report_mod.generar_reporte_semanal()
    finally:
        report_mod.leer_pestana = orig_leer
        report_mod.generar_texto = orig_texto
        report_mod.enviar_correo = orig_correo
        report_mod.guardar_reporte = orig_guardar
    return resultado, correos, guardados


resultado_rep, correos_rep, guardados_rep = _probar_reporte()
caso("(a) El reporte cuenta bien y el correo es prosa, no JSON",
     resultado_rep["mensajes_atendidos"] == 1
     and resultado_rep["citas_agendadas"] == 1
     and bool(correos_rep)
     and "Esta semana atendimos bien." in correos_rep[0][2]
     and "{" not in correos_rep[0][2],
     f"resultado={resultado_rep}, correo={correos_rep}")
caso("(a) El reporte se guarda en la hoja Reporte",
     bool(guardados_rep) and guardados_rep[0][3] == 1,
     f"guardados={guardados_rep}")

# ---------- (b) Seguridad ----------

caso("(b) Sin clave configurada, la clave de dueño nunca pasa",
     token_admin_ok("cualquier", "") is False
     and token_admin_ok(None, "clave") is False)
caso("(b) Con clave, solo pasa la exacta",
     token_admin_ok("clave-secreta", "clave-secreta") is True
     and token_admin_ok("otra", "clave-secreta") is False
     and token_admin_ok("", "clave-secreta") is False)

cuerpo = b'{"entry": []}'
firma_buena = "sha256=" + hmac.new(b"secreto-meta", cuerpo, hashlib.sha256).hexdigest()
caso("(b) La firma de Meta se verifica: buena pasa, mala no",
     verificar_firma_meta(cuerpo, firma_buena, "secreto-meta") is True
     and verificar_firma_meta(b"otro cuerpo", firma_buena, "secreto-meta") is False
     and verificar_firma_meta(cuerpo, None, "secreto-meta") is False
     and verificar_firma_meta(cuerpo, "sin-prefijo", "secreto-meta") is False)
caso("(b) Sin secreto de Meta, se acepta (con aviso en salud)",
     verificar_firma_meta(cuerpo, None, "") is True)

# ---------- (c) Perfil del negocio ----------

def _poner_perfil(nombre="", tipo="una clínica", recep="Ana"):
    orig = (settings.negocio_nombre, settings.negocio_tipo, settings.recepcionista_nombre)
    settings.negocio_nombre = nombre
    settings.negocio_tipo = tipo
    settings.recepcionista_nombre = recep
    return orig


def _quitar_perfil(orig):
    settings.negocio_nombre, settings.negocio_tipo, settings.recepcionista_nombre = orig


orig = _poner_perfil()
try:
    caso("(c) Sin nombre, la frase de cierre es neutra (no dice 'clínica')",
         negocio_mod.frase_cierre() == "El negocio ya cerró por hoy, pero yo te atiendo igual",
         negocio_mod.frase_cierre())
    prompt = agent_mod.guion()
    caso("(c) El guion usa el perfil: Ana, recepcionista de una clínica",
         "Te llamas Ana" in prompt and "recepcionista de una clínica" in prompt
         and "El negocio ya cerró por hoy, pero yo te atiendo igual" in prompt
         and "La clínica ya cerró" not in prompt,
         prompt[:200])
    texto, viol = revision_mod.revisar_respuesta(
        "Con gusto te atiendo, ahorita ya cerramos pero abrimos mañana.", {}, "")
    caso("(c) R3 usa la frase neutra del perfil",
         "el negocio ya cerró por hoy, pero yo te atiendo igual" in texto.lower()
         and "ya cerramos" not in texto.lower() and viol == ["R3"],
         f"salió: {texto!r} {viol}")
finally:
    _quitar_perfil(orig)

orig = _poner_perfil(nombre="Clínica Dental Sonrisa", tipo="una clínica dental", recep="Ana")
try:
    caso("(c) Con nombre, la frase usa el nombre real",
         negocio_mod.frase_cierre() == "En Clínica Dental Sonrisa ya cerraron por hoy, pero yo te atiendo igual",
         negocio_mod.frase_cierre())
    caso("(c) Con nombre, el guion dice de qué negocio es recepcionista",
         "recepcionista de Clínica Dental Sonrisa" in agent_mod.guion(),
         agent_mod.guion()[:200])
finally:
    _quitar_perfil(orig)

orig = _poner_perfil(nombre="", tipo="un restaurante", recep="Luis")
try:
    caso("(c) Otro giro y otro nombre: el guion cambia, el código no",
         "Te llamas Luis" in agent_mod.guion()
         and "recepcionista de un restaurante" in agent_mod.guion(),
         agent_mod.guion()[:200])
finally:
    _quitar_perfil(orig)

# ---------- (d) Salud al arrancar ----------

class DepsSalud:
    def __init__(self):
        self.diagnostico = []

    def registrar_diagnostico(self, fecha, componente, estado, detalle,
                              telefono="", contexto=""):
        self.diagnostico.append((componente, estado, detalle))


def _salud_con(gemini_ok=True, sheets_ok=True, calendar_ok=True,
               whatsapp_status=200, gmail=True, owner="dueno@real.com",
               admin=True, meta=True):
    d = DepsSalud()
    orig_gemini = salud_mod.gemini.generar_texto
    orig_sheets = salud_mod.sheets.leer_control
    orig_booking = salud_mod.booking.hora_libre
    orig_requests = salud_mod.requests
    orig_vals = (settings.gmail_user, settings.gmail_app_password,
                 settings.owner_email, settings.admin_token, settings.meta_app_secret)

    def texto_falso(prompt, json_mode=True):
        if not gemini_ok:
            raise RuntimeError("Gemini devolvió 503")
        return "OK"

    def control_falso():
        if not sheets_ok:
            raise RuntimeError("No encontré las credenciales de Google.")
        return {"bot_activo": "SI"}

    def libre_falso(fecha_iso):
        if not calendar_ok:
            raise RuntimeError("Calendar no responde.")
        return True

    class _Resp:
        def __init__(self, status):
            self.status_code = status
            self.text = "error" if status != 200 else "{}"

    class _Requests:
        def get(self, url, headers=None, timeout=None):
            return _Resp(whatsapp_status)

    salud_mod.gemini.generar_texto = texto_falso
    salud_mod.sheets.leer_control = control_falso
    salud_mod.booking.hora_libre = libre_falso
    salud_mod.requests = _Requests()
    settings.gmail_user = "dueno@gmail.com" if gmail else ""
    settings.gmail_app_password = "clave-app" if gmail else ""
    settings.owner_email = owner
    settings.admin_token = "clave-dueno" if admin else ""
    settings.meta_app_secret = "secreto" if meta else ""
    try:
        return d, salud_mod.revisar_salud(d)
    finally:
        salud_mod.gemini.generar_texto = orig_gemini
        salud_mod.sheets.leer_control = orig_sheets
        salud_mod.booking.hora_libre = orig_booking
        salud_mod.requests = orig_requests
        (settings.gmail_user, settings.gmail_app_password, settings.owner_email,
         settings.admin_token, settings.meta_app_secret) = orig_vals


d, res = _salud_con()
estados = {r["componente"]: r["estado"] for r in res}
caso("(d) Salud todo bien: 8 componentes en OK y en Diagnóstico",
     len(res) == 8 and all(e == "OK" for e in estados.values())
     and len(d.diagnostico) == 8,
     f"estados={estados}")

d, res = _salud_con(gemini_ok=False, whatsapp_status=401, gmail=False, admin=False, meta=False)
estados = {r["componente"]: r["estado"] for r in res}
caso("(d) Salud con fallos: Gemini FALLO, token 401 FALLO, lo demás AVISO",
     estados.get("gemini") == "FALLO"
     and estados.get("whatsapp") == "FALLO"
     and estados.get("gmail") == "AVISO"
     and estados.get("admin_token") == "AVISO"
     and estados.get("meta_firma") == "AVISO"
     and estados.get("sheets") == "OK",
     f"estados={estados}")
caso("(d) La salud no rompe el arranque aunque todo falle",
     _salud_con(gemini_ok=False, sheets_ok=False, calendar_ok=False,
                whatsapp_status=500, gmail=False, owner="dueno@empresa.com",
                admin=False, meta=False)[1] is not None)

# ---------- (e) Sheets con caché ----------

class _ServicioFalso:
    def __init__(self):
        self.llamadas_get = 0
        self.valores = {"values": [["telefono", "nombre"], ["521", "Jose"]]}

    def values(self):
        return self

    def get(self, spreadsheetId=None, range=None):
        self.llamadas_get += 1
        return self

    def append(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        return self

    def update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        return self

    def clear(self, spreadsheetId=None, range=None):
        return self

    def execute(self):
        return dict(self.valores)


servicio = _ServicioFalso()
orig_servicio = sheets_mod._servicio_sheets
sheets_mod._servicio_sheets = lambda: servicio
sheets_mod._CACHE.clear()
try:
    filas1 = sheets_mod.leer_pestana("Clientes")
    filas2 = sheets_mod.leer_pestana("Clientes")
    caso("(e) Dos lecturas seguidas de Clientes hacen UNA llamada a Google",
         servicio.llamadas_get == 1 and filas1 == filas2
         and filas1[0].get("nombre") == "Jose",
         f"llamadas={servicio.llamadas_get}, filas={filas1}")
    sheets_mod.agregar_fila("Clientes", ["x", "y"])
    sheets_mod.leer_pestana("Clientes")
    caso("(e) Después de escribir, la caché se borra y se vuelve a leer",
         servicio.llamadas_get == 2,
         f"llamadas={servicio.llamadas_get}")
    fila = sheets_mod._fila_cliente_por_telefono("521")
    caso("(e) Buscar un cliente reusa la caché (no suma llamadas)",
         fila is not None and fila[0] == 2 and fila[1]["nombre"] == "Jose"
         and servicio.llamadas_get == 2,
         f"fila={fila}, llamadas={servicio.llamadas_get}")
finally:
    sheets_mod._servicio_sheets = orig_servicio
    sheets_mod._CACHE.clear()

# ---------- (f) Buzón persistente ----------

import tempfile

lotes1 = []
lotes2 = []
with tempfile.TemporaryDirectory() as tmp:
    ruta = os.path.join(tmp, "buzon.json")
    ag1 = Agrupador(lambda t, n, x, w: lotes1.append((t, x)), espera_segundos=60, archivo=ruta)
    assert ag1.agregar("521", "hola", wamid="w1", nombre="Jose") is True
    assert ag1.agregar("521", "¿cuánto cuesta?", wamid="w2") is True
    assert ag1.agregar("521", "hola", wamid="w1") is False  # duplicado
    import json as _json
    guardado = _json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else {}
    # (v3.20.4) El archivo guarda entradas [timestamp, seq, texto,
    # wamid]; el texto es el tercer campo.
    _entradas = guardado.get("pendientes", {}).get("521", {}).get("entradas", [])
    caso("(f) El buzón se guarda en disco al agregar",
         [e[2] for e in _entradas] == ["hola", "¿cuánto cuesta?"],
         f"guardado={guardado}")
    ag2 = Agrupador(lambda t, n, x, w: lotes2.append((t, x)), espera_segundos=60, archivo=ruta)
    n = ag2.cargar()
    caso("(f) Al arrancar, los lotes pendientes se recuperan",
         n == 1, f"recuperados={n}")
    caso("(f) Un wamid ya visto sigue siendo duplicado tras recargar",
         ag2.agregar("521", "hola", wamid="w1") is False)
    ag2.procesar_ahora("521")
    caso("(f) El lote recuperado se procesa con los dos mensajes juntos",
         lotes2 == [("521", ["hola", "¿cuánto cuesta?"])],
         f"lotes={lotes2}")

# ---------- (g) Archivos vigentes ----------

raiz = os.path.dirname(os.path.abspath(__file__))
app_txt = open(os.path.join(raiz, "app.py"), encoding="utf-8").read()
env_txt = open(os.path.join(raiz, ".env.example"), encoding="utf-8").read()
inst_txt = open(os.path.join(raiz, "instalar.py"), encoding="utf-8").read()
caso("(g) La app es la versión 3.20.8",
     'version="3.20.8"' in app_txt or "VERSION = \"3.20.8\"" in app_txt,
     "versión no actualizada")
caso("(g) .env.example trae modelos vivos, no los retirados",
     "gemini-4-hydrogen" in env_txt and "gemini-3.8-flash" in env_txt
     and "gemini-2.0-flash" not in env_txt and "gemini-2.5-flash" not in env_txt
     and "ESPERA_AGRUPAR_SEGUNDOS=15" in env_txt
     and "ADMIN_TOKEN" in env_txt and "META_APP_SECRET" in env_txt,
     "el ejemplo sigue con modelos muertos o sin las claves nuevas")
caso("(g) El instalador escanea archivos (nunca se desactualiza) y no dice '7 segundos'",
     "os.listdir" in inst_txt and "7 segundos" not in inst_txt
     and "test_" in inst_txt and "robot/" in inst_txt,
     "el instalador está desactualizado")
caso("(g) Ya no hay print() sueltos en el código del robot",
     all("print(" not in open(os.path.join(raiz, f), encoding="utf-8").read()
         for f in ["app.py", "robot/logic.py", "robot/gemini.py", "robot/sheets.py"]),
     "queda un print en app.py, logic.py, gemini.py o sheets.py")
req_txt = open(os.path.join(raiz, "requirements.txt"), encoding="utf-8").read()
caso("(g) requirements.txt trae python-multipart (la página /pausa lo usa)",
     "python-multipart" in req_txt,
     "falta python-multipart en requirements.txt")

print(f"\n{TOTAL[0] - len(FALLOS)}/{TOTAL[0]} casos pasaron.")
if FALLOS:
    print("Fallaron:", ", ".join(FALLOS))
    sys.exit(1)
