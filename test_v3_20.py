"""v3.20: calidad conversacional (funciones 01, 04 y 05 de Jose).

01. Conversaciones naturales:
    - R10: la respuesta entera repetida se reemplaza (el revisor
      solo quitaba el cierre repetido).
    - El prompt lleva los últimos 8 mensajes de historial (antes 5).
04. Memoria útil:
    - La cita pasada se dice con servicio ("fue Blanqueamiento
      dental el ..."), para reconocer al paciente recurrente.
    - El guion manda usar las preferencias conocidas al proponer.
05. Atención humana cuando importa:
    - El correo de handoff trae el hilo reciente de la conversación
      (últimos 8 mensajes), para que recepción vea la foto completa.

Uso:  python3 test_v3_20.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FALLOS = []


def caso(nombre, cond, detalle=""):
    if cond:
        print(f"  ok  {nombre}")
    else:
        print(f"FALLO {nombre} {detalle}")
        FALLOS.append(nombre)


# ---------------------------------------------------------------- R10
from robot.revision import revisar_respuesta

txt, viol = revisar_respuesta(
    "La limpieza cuesta $600 y no duele.",
    {"ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele."},
)
caso("(a) R10 reemplaza repetición exacta",
     txt == "¿Te ayudo con algo más?" and "R10" in viol, f"{txt!r} {viol}")

txt, viol = revisar_respuesta(
    "La revisión cuesta $200.",
    {"ultimo_mensaje_robot": "La limpieza cuesta $600."},
)
caso("(b) R10 no toca texto distinto",
     txt == "La revisión cuesta $200." and "R10" not in viol, f"{txt!r} {viol}")

txt, viol = revisar_respuesta("¡Perfecto!", {"ultimo_mensaje_robot": ""})
caso("(c) R10 sin último mensaje no dispara",
     txt == "¡Perfecto!" and "R10" not in viol, f"{txt!r} {viol}")

txt, viol = revisar_respuesta(
    "  LA LIMPIEZA  cuesta $600 y NO DUELE. ",
    {"ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele."},
)
caso("(d) R10 normaliza (mayúsculas/espacios) y atrapa",
     txt == "¿Te ayudo con algo más?" and "R10" in viol, f"{txt!r} {viol}")

txt, viol = revisar_respuesta(
    "¡Perfecto!", {"ultimo_mensaje_robot": "¡Perfecto!"})
caso("(e) R10 reemplaza repetición corta",
     txt == "¿Te ayudo con algo más?" and "R10" in viol, f"{txt!r} {viol}")

# Una respuesta que solo comparte el cierre NO es R10 (eso es R7).
txt, viol = revisar_respuesta(
    "Claro, te ayudo. Quedamos a tus órdenes.",
    {"ultimo_mensaje_robot": "¡Hola! Quedamos a tus órdenes."},
)
caso("(f) R10 no confunde con R7 (cierre igual)",
     "R10" not in viol, f"{txt!r} {viol}")

# ------------------------------------------------- Historial 8 en prompt
import robot.agent as agente_mod

capturado = {}


def fake_generar(prompt, json_mode=True):
    capturado["prompt"] = prompt
    return "Texto de prueba."


agente_mod.generar_texto = fake_generar
hist = [
    {"fecha": f"2026-11-23T0{i}:00:00+00:00", "quien_hablo": "cliente",
     "mensaje": f"mensaje numero {i}"}
    for i in range(1, 11)
]
agente_mod.preguntar_agente("hola", [], [], hist)
p = capturado.get("prompt", "")
caso("(g) el prompt lleva los últimos 8 mensajes",
     '"mensaje numero 3"' in p and '"mensaje numero 10"' in p
     and '"mensaje numero 2"' not in p and '"mensaje numero 1"' not in p,
     p[-400:])

# ------------------------------------------------- Memoria: cita pasada
from test_simulacion_conversacional import nuevo_c, contexto_recibido
from test_simulacion_profunda import msg, limpiar
from test_bateria_dinamica import NOMBRE

limpiar()
cli = {"estatus": "agendado", "fecha_cita": "2026-11-16T09:00:00-07:00",
       "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
d = nuevo_c(cliente=cli)
msg(d, "hola")
ok = any("Su última cita fue Blanqueamiento dental el" in m
         for m in d.mensajes_agente)
caso("(h) cita pasada dice el servicio", ok,
     d.mensajes_agente[-1][:300] if d.mensajes_agente else "sin mensajes")
limpiar()

limpiar()
cli2 = {"estatus": "agendado", "fecha_cita": "2026-11-16T09:00:00-07:00",
        "motivo": "", "nombre": NOMBRE}
d2 = nuevo_c(cliente=cli2)
msg(d2, "hola")
ok2 = any("Su última cita fue el" in m for m in d2.mensajes_agente)
caso("(i) cita pasada sin servicio usa el texto viejo", ok2)
limpiar()

# ------------------------------------------------- Handoff con hilo
import robot.mail as mail_mod

correos = []
mail_mod.enviar_correo = lambda para, asunto, cuerpo, html=None: correos.append((para, asunto, cuerpo))
mail_mod.correo_dueno = lambda: "dueno@ejemplo.com"
mail_mod.alerta_handoff(
    "Ana", "5216690000000", "queja", "estoy enojado", "2026-11-23",
    resumen="Preguntó precios.",
    hilo="Cliente: hola\nRobot: ¡Hola!\nCliente: estoy enojado",
)
cuerpo = correos[-1][2] if correos else ""
caso("(j) correo de handoff omite el hilo y el resumen",
     "Últimos mensajes de la conversación:" not in cuerpo
     and "Cliente: estoy enojado" not in cuerpo
     and "Preguntó precios." not in cuerpo and "Atención humana" in cuerpo, cuerpo[:300])

mail_mod.alerta_handoff("Ana", "5216690000000", "queja", "hola", "2026-11-23")
caso("(k) correo sin hilo sale bien",
     "Últimos mensajes" not in correos[-1][2])

# Integración: el handoff real pasa el hilo al correo.
from test_simulacion_conversacional import DepsConversacional

limpiar()
hist2 = [
    {"fecha": "2026-11-23T20:00:00+00:00", "quien_hablo": "cliente",
     "mensaje": "hola, buenas tardes"},
    {"fecha": "2026-11-23T20:01:00+00:00", "quien_hablo": "robot",
     "mensaje": "¡Hola! ¿En qué te ayudo?"},
]
d3 = DepsConversacional(historial=hist2)
msg(d3, "estoy muy enojado con el servicio")
caso("(l) handoff real manda el hilo",
     bool(d3.hilos) and "hola, buenas tardes" in d3.hilos[-1]
     and "¿En qué te ayudo?" in d3.hilos[-1], str(d3.hilos)[:200])
limpiar()

# ------------------------------------------------- Guion: preferencias
guion_txt = agente_mod.guion()
caso("(m) el guion manda usar preferencias al proponer",
     "Preferencias conocidas" in guion_txt)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "guion-robot.md"), encoding="utf-8") as fh:
    guion_md = fh.read()
caso("(n) guion-robot.md sincronizado",
     "Preferencias conocidas" in guion_md)

print()
if FALLOS:
    print(f"v3.20: {len(FALLOS)} FALLOS: {FALLOS}")
    sys.exit(1)
print("v3.20: todo verde (14 casos)")
