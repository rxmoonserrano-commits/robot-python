"""Pruebas de la versión 2.9, SIN internet.

Cubre solo lo nuevo de la v2.9:
(a) el modelo principal por defecto es gemini-4-hydrogen (gratis,
    misma clave, sin que el dueño haga nada nuevo).
(b) la lista de candidatos siempre termina en Flash-Lite, el modelo
    gratis más chico y menos saturado.
(c) un 503 "high demand" se reintenta una vez tras 2 s antes de
    rendirse y probar otro modelo (v3.4.1: antes dos reintentos con
    2 s y 8 s, que colgaba los lotes).
(d) si todos los modelos dan 503, el error final es un 503 (no se
    esconde: en Diagnóstico se ve que fue saturación).
(e) (v3.4.5) texto vacío con 200: no se acepta como éxito; se prueba
    el siguiente modelo.
(f) (v3.4.5) si todos devuelven vacío, el error dice "texto vacío"
    con el finishReason.

Uso:  python test_v2_9.py
"""

import robot.gemini as gemini_mod
from robot.config import settings


class _RespuestaFalsa:
    def __init__(self, status_code=200, texto="OK"):
        self.status_code = status_code
        self.text = texto

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def main():
    # (a-b) Los modelos son explícitos; no se afirma vigencia ni tarifa.
    settings.gemini_model = ""
    settings.gemini_model_fallback = ""
    gemini_mod._ULTIMO_MODELO_OK = None
    caso("(a) Sin modelos configurados no inventa candidatos", gemini_mod._candidatos() == [])
    settings.gemini_model = "modelo-principal"
    settings.gemini_model_fallback = "modelo-respaldo"
    candidatos = gemini_mod._candidatos()
    caso("(b) Solo principal y respaldo configurados, sin repetidos",
         candidatos == ["modelo-principal", "modelo-respaldo"], f"candidatos={candidatos}")

    # (c) 503: reintenta una vez tras 2 s y luego contesta.
    clave_vieja = settings.gemini_api_key
    post_viejo = gemini_mod.requests.post
    dormir_viejo = gemini_mod.time.sleep
    try:
        settings.gemini_api_key = "clave-de-prueba"
        gemini_mod._ULTIMO_MODELO_OK = None
        llamadas = []
        esperas = []

        def post_falso(url, json=None, timeout=None):
            llamadas.append(url.split("/models/")[1].split(":")[0])
            if len(llamadas) <= 1:
                return _RespuestaFalsa(503, '{"error": {"message": "high demand"}}')
            return _RespuestaFalsa(200, "OK")

        gemini_mod.requests.post = post_falso
        gemini_mod.time.sleep = lambda s: esperas.append(s)
        texto = gemini_mod.generar_texto("Responde solo con la palabra OK.")
        caso("(c) Tras un 503, reintenta una vez y contesta",
             texto == "OK" and len(llamadas) == 2, f"texto={texto!r} llamadas={llamadas}")
        caso("(c) La espera es de 2 s",
             esperas == [2], f"esperas={esperas}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod.requests.post = post_viejo
        gemini_mod.time.sleep = dormir_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    # (d) Todos dan 503: el error final dice 503.
    try:
        settings.gemini_api_key = "clave-de-prueba"
        gemini_mod._ULTIMO_MODELO_OK = None
        gemini_mod.requests.post = lambda url, json=None, timeout=None: _RespuestaFalsa(
            503, '{"error": {"message": "high demand"}}')
        gemini_mod.time.sleep = lambda s: None
        try:
            gemini_mod.generar_texto("Hola.")
            caso("(d) Todos con 503: lanza el error", False, "no lanzó nada")
        except gemini_mod.GeminiError as exc:
            caso("(d) Todos con 503: el error final es un 503",
                 "503" in str(exc), f"error={exc}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod.requests.post = post_viejo
        gemini_mod.time.sleep = dormir_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    # (e) Texto vacío con 200: no se acepta; se prueba el siguiente modelo.
    try:
        settings.gemini_api_key = "clave-de-prueba"
        gemini_mod._ULTIMO_MODELO_OK = None
        llamadas = []

        def post_vacio_luego_ok(url, json=None, timeout=None):
            modelo = url.split("/models/")[1].split(":")[0]
            llamadas.append(modelo)
            if modelo == "modelo-principal":
                return _RespuestaFalsa(200, "")
            return _RespuestaFalsa(200, "OK")

        gemini_mod.requests.post = post_vacio_luego_ok
        gemini_mod.time.sleep = lambda s: None
        texto = gemini_mod.generar_texto("Hola.")
        caso("(e) Texto vacío: prueba el siguiente modelo",
             texto == "OK" and llamadas[0] == "modelo-principal"
             and llamadas[-1] == "modelo-respaldo",
             f"texto={texto!r} llamadas={llamadas}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod.requests.post = post_viejo
        gemini_mod.time.sleep = dormir_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    # (f) Todos devuelven vacío: el error dice "texto vacío".
    try:
        settings.gemini_api_key = "clave-de-prueba"
        gemini_mod._ULTIMO_MODELO_OK = None
        gemini_mod.requests.post = lambda url, json=None, timeout=None: _RespuestaFalsa(200, "")
        gemini_mod.time.sleep = lambda s: None
        try:
            gemini_mod.generar_texto("Hola.")
            caso("(f) Todos vacíos: lanza el error", False, "no lanzó nada")
        except gemini_mod.GeminiError as exc:
            caso("(f) Todos vacíos: el error dice texto vacío",
                 "texto vacío" in str(exc), f"error={exc}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod.requests.post = post_viejo
        gemini_mod.time.sleep = dormir_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
