"""Pruebas de la versión 2.8, SIN internet.

Cubre solo lo nuevo de la v2.8:
(a) un timeout de Gemini se reintenta (antes salía volando sin
    reintentar ni probar el siguiente modelo) y el tiempo de espera
    es de 45 s (v3.4.1: antes 120 s, que colgaba los lotes).
(b) Gemini contesta en prosa, sin JSON: esa prosa ES la respuesta al
    cliente, no se tira a la basura.
(c) Gemini contesta un JSON roto: respuesta segura, y el motivo dice
    qué devolvió (para verlo en Diagnóstico).
(d) Gemini no contesta (error de red): el motivo lleva el error real,
    no un texto genérico.
(e) el historial que se le manda a Gemini se recorta a los últimos 5
    mensajes (antes eran 20 y el prompt era enorme).

Uso:  python test_v2_8.py
"""

import json

import robot.agent as agent_mod
import robot.gemini as gemini_mod
from robot.agent import preguntar_agente
from robot.config import settings

CONOCIMIENTO = [
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
]
FOTOS = []


class _RespuestaFalsa:
    def __init__(self, status_code=200, texto="Hola, ¿qué necesitas?"):
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
    # (a) Timeout: se reintenta y contesta; el timeout es de 45 s.
    clave_vieja = settings.gemini_api_key
    post_viejo = gemini_mod.requests.post
    llamadas = []
    try:
        settings.gemini_api_key = "clave-de-prueba"
        gemini_mod._ULTIMO_MODELO_OK = None

        def post_falso(url, json=None, timeout=None):
            llamadas.append(timeout)
            if len(llamadas) == 1:
                raise gemini_mod.requests.exceptions.ReadTimeout("read timed out")
            return _RespuestaFalsa(200, "OK")

        gemini_mod.requests.post = post_falso
        texto = gemini_mod.generar_texto("Responde solo con la palabra OK.")
        caso("(a) Tras un timeout, reintenta y contesta",
             texto == "OK" and len(llamadas) == 2, f"texto={texto!r} llamadas={len(llamadas)}")
        caso("(a) El tiempo de espera es de 45 segundos",
             llamadas == [45, 45], f"llamadas={llamadas}")
    finally:
        settings.gemini_api_key = clave_vieja
        gemini_mod.requests.post = post_viejo
        gemini_mod._ULTIMO_MODELO_OK = None

    # (b) Prosa sin JSON: se manda tal cual.
    generar_viejo = agent_mod.generar_texto
    try:
        agent_mod.generar_texto = lambda prompt: (
            "Hola, Jose Ramon. Buenas noches, dime qué necesitas y te atiendo.")
        r = preguntar_agente("buenas noches", CONOCIMIENTO, FOTOS, [])
        caso("(b) Prosa sin JSON: es la respuesta al cliente, sin fallo",
             r.respuesta_texto.startswith("Hola, Jose Ramon")
             and r.falla_tecnica is False and r.necesita_handoff == "no",
             f"r={r}")
    finally:
        agent_mod.generar_texto = generar_viejo

    # (c) JSON roto: respuesta segura con el detalle de lo que devolvió.
    try:
        agent_mod.generar_texto = lambda prompt: '{"respuesta_texto": "Hola,'
        r = preguntar_agente("hola", CONOCIMIENTO, FOTOS, [])
        caso("(c) JSON roto: 'dame un momento' y el motivo dice qué devolvió",
             r.falla_tecnica is True and "no es JSON" in r.motivo_handoff
             and "respuesta_texto" in r.motivo_handoff,
             f"r={r}")
    finally:
        agent_mod.generar_texto = generar_viejo

    # (d) Gemini no contesta: el motivo lleva el error real.
    try:
        def _falla(prompt):
            raise gemini_mod.GeminiError("Gemini tardó demasiado o se cortó la red")
        agent_mod.generar_texto = _falla
        r = preguntar_agente("hola", CONOCIMIENTO, FOTOS, [])
        caso("(d) Sin respuesta de Gemini: el motivo lleva el error real",
             r.falla_tecnica is True and "Gemini no contestó" in r.motivo_handoff
             and "tardó demasiado" in r.motivo_handoff,
             f"r={r}")
    finally:
        agent_mod.generar_texto = generar_viejo

    # (e) Historial recortado a los últimos 8 mensajes (v3.20; antes 5).
    try:
        prompts = []
        agent_mod.generar_texto = lambda prompt: (
            prompts.append(prompt),
            '{"respuesta_texto": "Hola.", "quiere_agendar": "no", '
            '"necesita_handoff": "no"}')[1]
        historial = [{"telefono": "1", "quien_hablo": "cliente", "mensaje": f"m{i}"}
                     for i in range(20)]
        r = preguntar_agente("hola", CONOCIMIENTO, FOTOS, historial)
        parte = prompts[0].split("mensajes viejos): ", 1)[1].split("\n\n", 1)[0]
        enviados = json.loads(parte)
        caso("(e) El historial que se manda son los últimos 8 mensajes",
             len(enviados) == 8 and enviados[0]["mensaje"] == "m12"
             and enviados[-1]["mensaje"] == "m19",
             f"enviados={len(enviados)}")
    finally:
        agent_mod.generar_texto = generar_viejo

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
