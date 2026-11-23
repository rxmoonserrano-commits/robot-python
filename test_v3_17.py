"""Pruebas de la v3.17: verificación de hechos + batería dinámica.

Jose pidió que la respuesta de la IA tenga inteligencia de verdad:
contexto, memoria, circunstancias, y que SEPA de qué habla. Esta
versión da el primer paso verificable:

- R9 en el revisor: ningún precio inventado. Si la respuesta trae
  un monto que no está en el Conocimiento, se desecha y se contesta
  con la frase segura del guion.
- Cortesía en el sí: "me va por favor" y "sí por favor" ahora sí
  confirman (la batería dinámica lo encontró). "gracias" sigue
  fuera, por el incidente del 12 de noviembre.
- Toque viejo en "Adelantar cita"/"Mover cita" ya no se queda en
  silencio: responde.
- Batería dinámica (test_bateria_dinamica.py): generador de
  estados y mensajes + invariantes + explorador adaptativo. Aquí
  se corre una pasada chica como prueba de humo.

Casos:
(a) R9: precio conocido pasa; precio inventado se desecha; sin
    lista de precios, R9 no aplica.
(b) Cortesía: "me va por favor" / "sí por favor" / "vale" son sí;
    "sí gracias" sigue sin serlo.
(c) Toque viejo en adelantar con propuesta nueva: responde.
(d) Batería dinámica: pasada chica sin violaciones.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.logic import (  # noqa: E402
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_afirmacion,
    atender_boton,
)
from robot.revision import precios_de_conocimiento, revisar_respuesta  # noqa: E402

TEL = "5216694608263"
AHORA = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
LUNES = "2026-11-23T10:00:00-07:00"

FALLOS = []
TOTAL = [0]


def caso(nombre, ok, detalle=""):
    TOTAL[0] += 1
    if ok:
        print(f"  ok  {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"  FAIL {nombre} :: {detalle}")


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()


CONOC = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "servicio", "pregunta_o_servicio": "Blanqueamiento dental",
     "respuesta_o_precio": "$1,800", "detalle": "Dura 60 minutos"},
]
PRECIOS = precios_de_conocimiento(CONOC)

# ---- (a) R9: ningún precio inventado ----
limpiar()
t, v = revisar_respuesta("La limpieza cuesta $600.", precios_conocidos=PRECIOS)
caso("(a) Precio conocido pasa", "R9" not in v and "$600" in t, f"{t} {v}")

t, v = revisar_respuesta("La limpieza cuesta $650.", precios_conocidos=PRECIOS)
caso("(a) Precio inventado se desecha", "R9" in v and "$650" not in t, f"{t} {v}")

t, v = revisar_respuesta("Te lo dejo en 500 pesos.", precios_conocidos=PRECIOS)
caso("(a) Descuento inventado se desecha", "R9" in v, f"{t} {v}")

t, v = revisar_respuesta("Cuesta $999.", precios_conocidos=None)
caso("(a) Sin lista de precios, R9 no aplica", "R9" not in v, f"{v}")

t, v = revisar_respuesta("Te atiendo a las 9:00, Av. del Mar 123.",
                         precios_conocidos=PRECIOS)
caso("(a) Hora y dirección no son precios", "R9" not in v, f"{v}")

# ---- (b) Cortesía en el sí ----
caso("(b) 'me va por favor' es sí", _es_afirmacion("me va por favor") is True)
caso("(b) 'sí por favor' es sí", _es_afirmacion("sí por favor") is True)
caso("(b) 'vale' es sí", _es_afirmacion("vale") is True)
caso("(b) 'sí gracias' sigue sin ser sí", _es_afirmacion("sí gracias") is False)

# ---- (c) Toque viejo en adelantar: no hay silencio ----
limpiar()


class DepsMin:
    def __init__(self):
        self.textos = []
        self.conversaciones = []

    def leer_robot_activo(self, telefono):
        return "SI"

    def registrar_conversacion(self, fecha, telefono, quien, texto, respondio, motivo):
        self.conversaciones.append(motivo)

    def enviar_texto(self, telefono, texto):
        self.textos.append(texto)


_CITAS_PENDIENTES[TEL] = {
    "nombre": "Jose Ramon", "motivo": "limpieza", "fecha_cita": LUNES,
    "fecha_bonita": "lunes 23 de noviembre a las 10:00",
    "creado_en": "2026-11-23T15:30:00+00:00",
    "profesional": "", "nombre_paciente": "", "relacion_paciente": "",
    "numero_paciente": "", "cita2": None,
}
d = DepsMin()
r = atender_boton(d, TEL, "Jose Ramon", "adelantar_cita",
                  con_ritmo=False, ahora=AHORA)
caso("(c) Toque viejo en adelantar responde (sin silencio)",
     len(d.textos) == 1 and "sigue en pie" in d.textos[0],
     f"textos={d.textos} r={r}")
limpiar()

# ---- (d) Batería dinámica: pasada chica sin violaciones ----
res = subprocess.run(
    [sys.executable, "test_bateria_dinamica.py", "--semilla", "7", "--casos", "50"],
    cwd=os.path.dirname(os.path.abspath(__file__)),
    capture_output=True, text=True, timeout=120)
caso("(d) Batería dinámica pasa sin violaciones",
     res.returncode == 0 and "Sin violaciones" in res.stdout,
     f"rc={res.returncode} {res.stdout[-300:]} {res.stderr[-300:]}")

print()
if FALLOS:
    print(f"FALLOS ({len(FALLOS)}): {FALLOS}")
    sys.exit(1)
print(f"{TOTAL[0]}/{TOTAL[0]} casos ok (test_v3_17)")
