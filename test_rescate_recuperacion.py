"""Prueba permanente v3.20.14: rescate de JSON roto + recuperación al arrancar.

Dos fallas vistas en vivo el 2026-11-25 con el número nuevo:
1. Gemini devolvió un JSON truncado (tope de tokens) y el cliente recibió
   el genérico "dame un momento" en vez de la respuesta real. Ahora el
   robot rescata respuesta_texto del JSON roto y la manda (AVISO, no FALLO),
   y el tope subió de 600 a 1500 tokens.
2. Render se reinició a mitad de un lote en proceso y dos mensajes
   quedaron registrados sin respuesta. Ahora, al arrancar, el robot busca
   en Conversaciones los mensajes de cliente sin respuesta y los atiende.

Uso: python3 test_rescate_recuperacion.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

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


# ---------- A. _extraer_respuesta_texto ----------

from robot.agent import _extraer_respuesta_texto  # noqa: E402

caso("(a) JSON truncado a media frase → texto hasta el fin",
     _extraer_respuesta_texto('{"respuesta_texto": "¡Hola, José Ramón! Qué buen')
     == "¡Hola, José Ramón! Qué buen")

caso("(b) JSON con texto de más al final → hasta la comilla de cierre",
     _extraer_respuesta_texto(
         '{"respuesta_texto": "La limpieza cuesta $600.", "quiere_agendar": "no"} EXTRA')
     == "La limpieza cuesta $600.")

caso("(c) Comillas escapadas dentro del texto → se desescapan",
     _extraer_respuesta_texto('{"respuesta_texto": "El precio es \\"especial\\" hoy para ti."}')
     == 'El precio es "especial" hoy para ti.')

caso("(d) Sin campo respuesta_texto → vacío",
     _extraer_respuesta_texto('{"otra_cosa": "hola"}') == "")

caso("(e) Texto vacío → vacío",
     _extraer_respuesta_texto('{"respuesta_texto": ""}') == "")

caso("(f) Escape \\n dentro del texto → salto de línea",
     _extraer_respuesta_texto('{"respuesta_texto": "Primera línea.\\nSegunda línea."}')
     == "Primera línea.\nSegunda línea.")

caso("(g) Texto que no es JSON → vacío",
     _extraer_respuesta_texto("Hola, ¿qué necesitas?") == "")

# ---------- B. preguntar_agente con JSON roto ----------

import robot.agent as agent_mod  # noqa: E402
from robot.agent import preguntar_agente  # noqa: E402

CONOCIMIENTO = [{"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
                 "respuesta_o_precio": "09:00 a 18:00", "detalle": ""}]
FOTOS = []
generar_viejo = agent_mod.generar_texto

try:
    # JSON truncado con respuesta_texto larga: se rescata y se manda.
    agent_mod.generar_texto = lambda prompt: (
        '{\n  "respuesta_texto": "¡Hola, José Ramón! Qué bueno que escribes. '
        'La limpieza dental cuesta $600 y dura 60 minutos. ¿Te agendo una cita?", '
        '"quiere_agendar": "si", "nom')
    r = preguntar_agente("hola, cuánto cuesta la limpieza?", CONOCIMIENTO, FOTOS, [])
    caso("(h) JSON truncado con texto rescatable → respuesta real, sin fallo",
         r.falla_tecnica is False and r.necesita_handoff == "no"
         and r.respuesta_texto.startswith("¡Hola, José Ramón!")
         and "La limpieza dental cuesta $600" in r.respuesta_texto,
         f"r={r}")
    caso("(i) El rescate deja aviso_json para Diagnóstico",
         bool(r.aviso_json), f"r={r}")

    # JSON roto sin nada rescatable: fallback de siempre.
    agent_mod.generar_texto = lambda prompt: '{"respuesta_texto": "Hola,'
    r = preguntar_agente("hola", CONOCIMIENTO, FOTOS, [])
    caso("(j) JSON roto sin rescate → 'dame un momento' con FALLO",
         r.falla_tecnica is True and "no es JSON" in r.motivo_handoff
         and r.respuesta_texto.startswith("Dame un momento"),
         f"r={r}")

    # Prosa: sin cambios.
    agent_mod.generar_texto = lambda prompt: "Hola, buenas noches, dime qué necesitas."
    r = preguntar_agente("buenas noches", CONOCIMIENTO, FOTOS, [])
    caso("(k) Prosa sin JSON: se manda tal cual, sin aviso",
         r.respuesta_texto.startswith("Hola") and r.falla_tecnica is False
         and not r.aviso_json, f"r={r}")

    # JSON válido: sin cambios, sin aviso.
    agent_mod.generar_texto = lambda prompt: (
        '{"respuesta_texto": "La limpieza cuesta $600.", "quiere_agendar": "no"}')
    r = preguntar_agente("cuánto cuesta", CONOCIMIENTO, FOTOS, [])
    caso("(l) JSON válido: respuesta normal, sin aviso",
         r.respuesta_texto == "La limpieza cuesta $600." and not r.aviso_json
         and r.falla_tecnica is False, f"r={r}")
finally:
    agent_mod.generar_texto = generar_viejo

# ---------- C. _mensajes_sin_respuesta (recuperación) ----------

from app import _mensajes_sin_respuesta  # noqa: E402

AHORA = datetime(2026, 11, 25, 22, 10, tzinfo=timezone.utc)


def fila(fecha, telefono, quien, mensaje, respondio="si", motivo=""):
    return {"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
            "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo}


def iso(dt):
    return dt.isoformat()


# (m) Mensaje respondido: no se recupera.
filas = [
    fila(iso(AHORA - timedelta(minutes=5)), "521111", "cliente", "hola"),
    fila(iso(AHORA - timedelta(minutes=5)), "521111", "robot", "¡Hola! ¿Qué necesitas?"),
]
caso("(m) Mensaje con respuesta → no se recupera",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {})

# (n) Mensaje sin respuesta reciente: se recupera.
filas = [
    fila(iso(AHORA - timedelta(minutes=3)), "521222", "cliente", "Hola buenas tardes"),
]
caso("(n) Mensaje sin respuesta reciente → se recupera",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {"521222": ["Hola buenas tardes"]})

# (o) Mensaje viejo (fuera de ventana): no se recupera.
filas = [
    fila(iso(AHORA - timedelta(hours=30)), "521333", "cliente", "hola"),
]
caso("(o) Mensaje viejo fuera de ventana → no se recupera",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {})

# (p) Silencio intencional (pausa): no se recupera.
filas = [
    fila(iso(AHORA - timedelta(minutes=3)), "521444", "cliente", "hola",
         respondio="no", motivo="humano activo hace menos de 2 horas"),
]
caso("(p) Silencio intencional → no se recupera",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {})

# (q) Respondido por humano: no se recupera.
filas = [
    fila(iso(AHORA - timedelta(minutes=3)), "521555", "cliente", "hola"),
    fila(iso(AHORA - timedelta(minutes=2)), "521555", "humano",
         "(la persona atendió el chat)", respondio="no"),
]
caso("(q) Respondido por humano → no se recupera",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {})

# (r) Dos mensajes sin respuesta del mismo teléfono: ambos, en orden.
filas = [
    fila(iso(AHORA - timedelta(minutes=4)), "521666", "cliente", "hola"),
    fila(iso(AHORA - timedelta(minutes=3)), "521666", "cliente",
         "cuánto cuesta la limpieza?"),
]
caso("(r) Dos mensajes sin respuesta → ambos en orden",
     _mensajes_sin_respuesta(filas, ahora=AHORA)
     == {"521666": ["hola", "cuánto cuesta la limpieza?"]})

# (s) Mensaje respondido + uno nuevo sin respuesta: solo el nuevo.
filas = [
    fila(iso(AHORA - timedelta(minutes=10)), "521777", "cliente", "hola"),
    fila(iso(AHORA - timedelta(minutes=10)), "521777", "robot", "¡Hola!"),
    fila(iso(AHORA - timedelta(minutes=2)), "521777", "cliente", "okay gracias"),
]
caso("(s) Solo se recupera lo que quedó después de la última respuesta",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {"521777": ["okay gracias"]})

# (t) Filas rotas no rompen el escaneo.
filas = [
    {"fecha": "no-es-fecha", "telefono": "521888", "quien_hablo": "cliente",
     "mensaje": "hola", "robot_respondio": "si", "motivo": ""},
    {"fecha": iso(AHORA - timedelta(minutes=1)), "telefono": "",
     "quien_hablo": "cliente", "mensaje": "hola", "robot_respondio": "si",
     "motivo": ""},
    fila(iso(AHORA - timedelta(minutes=1)), "521888", "cliente", "buenas tardes"),
]
caso("(t) Filas rotas se ignoran sin romper",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {"521888": ["buenas tardes"]})

# (u) Mismo mensaje re-registrado por reinicios → se recupera una vez.
filas = [
    fila(iso(AHORA - timedelta(minutes=5)), "521999", "cliente", "Hola buenas tardes"),
    fila(iso(AHORA - timedelta(minutes=4)), "521999", "cliente", "Hola buenas tardes"),
    fila(iso(AHORA - timedelta(minutes=3)), "521999", "cliente", "Hola buenas tardes"),
]
caso("(u) Mismo mensaje re-registrado por reinicios → se recupera una vez",
     _mensajes_sin_respuesta(filas, ahora=AHORA) == {"521999": ["Hola buenas tardes"]})

# (v) Duplicado intercalado → orden conservado, sin repetir.
filas = [
    fila(iso(AHORA - timedelta(minutes=5)), "521999", "cliente", "hola"),
    fila(iso(AHORA - timedelta(minutes=4)), "521999", "cliente", "cuánto cuesta?"),
    fila(iso(AHORA - timedelta(minutes=3)), "521999", "cliente", "hola"),
]
caso("(v) Duplicado intercalado → orden conservado, sin repetir",
     _mensajes_sin_respuesta(filas, ahora=AHORA)
     == {"521999": ["hola", "cuánto cuesta?"]})

# ---------- D. Recuperación en serie (v3.20.15) ----------

import app as app_mod  # noqa: E402


class AgrupadorFalso:
    """Registra el orden de llamadas: para probar que la recuperación
    procesa de a un teléfono (agregar + procesar_ahora por teléfono),
    nunca todos los lotes a la vez."""

    def __init__(self):
        self.llamadas = []

    def agregar(self, telefono, texto, **_kw):
        self.llamadas.append(("agregar", telefono, texto))
        return True

    def procesar_ahora(self, telefono):
        self.llamadas.append(("procesar_ahora", telefono))
        return True


filas_rec = [
    fila(iso(AHORA - timedelta(minutes=3)), "521999", "cliente", "hola buenas tardes"),
    fila(iso(AHORA - timedelta(minutes=2)), "521999", "cliente", "hola buenas tardes"),
    fila(iso(AHORA - timedelta(minutes=2)), "521888", "cliente", "okay gracias"),
]
falso = AgrupadorFalso()
leer_viejo = app_mod.sheets.leer_pestana
diag_viejo = app_mod.sheets.registrar_diagnostico
agrupador_viejo = app_mod._AGRUPADOR
try:
    app_mod.sheets.leer_pestana = lambda pestana, **_kw: filas_rec
    app_mod.sheets.registrar_diagnostico = lambda *a, **kw: None
    app_mod._AGRUPADOR = falso
    app_mod._recuperar_sin_respuesta()
finally:
    app_mod.sheets.leer_pestana = leer_viejo
    app_mod.sheets.registrar_diagnostico = diag_viejo
    app_mod._AGRUPADOR = agrupador_viejo

caso("(w) Recuperación en serie: un teléfono a la vez, sin duplicados",
     falso.llamadas == [
         ("agregar", "521999", "hola buenas tardes"),
         ("procesar_ahora", "521999"),
         ("agregar", "521888", "okay gracias"),
         ("procesar_ahora", "521888"),
     ], f"llamadas={falso.llamadas}")

# ---------- E. Espera de salud antes de recuperar (v3.20.15) ----------

from robot import estado_servidor  # noqa: E402

# Con salud no lista y tope corto: termina por el tope, sin colgarse.
app_mod._esperar_salud_para_recuperar(intentos=2, espera_segundos=0)
caso("(x) Espera de salud con tope: no se cuelga si salud nunca termina", True)

# Con salud lista: regresa de inmediato.
estado_servidor.marcar_salud_lista()
app_mod._esperar_salud_para_recuperar(intentos=2, espera_segundos=0)
caso("(y) Espera de salud: con salud lista regresa al instante",
     estado_servidor.foto().get("salud_lista") is True)

print(f"\n{pasadas} OK, {fallidas} fallidas")
sys.exit(1 if fallidas else 0)
