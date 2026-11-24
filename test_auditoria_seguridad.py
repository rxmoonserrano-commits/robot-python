"""Auditoría v3.20.4 — Área 4: seguridad y abuso.

Reproduce los hallazgos ANTES de corregir:
- D1: los botones saltaban el Limitador: tocar "Hablar con persona"
  dos veces mandaba DOS correos de handoff. El cliente debe recibir
  sus dos respuestas por WhatsApp, pero el dueño solo UN correo
  (ventana de 30 min por teléfono).
- D2: el dedup es por teléfono: dos clientes distintos sí generan
  dos correos.
- D3: el helper _handoff_repetido: primer aviso pasa, repetido se
  frena, las URGENCIAS nunca se frenan (una segunda urgencia sí
  avisa), y pasada la ventana vuelve a avisar.
- D4: cableado en app.py: los botones también pasan por un
  Limitador (30/min) para que un tap repetido no inunde WhatsApp.
- D5: cableado en logic.py: el dedup está en los 3 sitios de
  handoff disparados por el cliente (botón, texto, silencio).

Corre con: python3 test_auditoria_seguridad.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    atender_boton,
)
from test_bateria_dinamica import AHORA_ABIERTO, NOMBRE, TEL  # noqa: E402
from test_pulida_agrupamiento import DepsAgrupamiento  # noqa: E402

AHORA = AHORA_ABIERTO
TEL2 = "5216694608264"


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()


def d1_doble_tap_un_correo():
    d = DepsAgrupamiento(ahora=AHORA)
    atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    correos = len(d.alertas_handoff)
    respuestas = len(d.textos)
    ok = correos == 1 and respuestas == 2
    return ok, f"correos={correos} respuestas={respuestas}"


def d2_dos_telefonos_dos_correos():
    d = DepsAgrupamiento(ahora=AHORA)
    atender_boton(d, TEL, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    atender_boton(d, TEL2, NOMBRE, "hablar_persona", con_ritmo=False, ahora=AHORA)
    correos = len(d.alertas_handoff)
    ok = correos == 2
    return ok, f"correos={correos}"


def d3_helper_dedup():
    from robot.logic import _MOTIVO_URGENCIA, _handoff_repetido

    class Dummy:
        pass

    d = Dummy()
    r1 = _handoff_repetido(d, TEL, "pedir persona")    # False: primer aviso
    r2 = _handoff_repetido(d, TEL, "pedir persona")    # True: repetido
    r3 = _handoff_repetido(d, TEL, _MOTIVO_URGENCIA)   # False: exenta
    r4 = _handoff_repetido(d, TEL, _MOTIVO_URGENCIA)   # False: exenta siempre
    d._ultimo_handoff_correo[TEL] = time.monotonic() - 3600
    r5 = _handoff_repetido(d, TEL, "pedir persona")    # False: ventana pasó
    ok = (r1 is False and r2 is True and r3 is False
          and r4 is False and r5 is False)
    return ok, f"r={r1}/{r2}/{r3}/{r4}/{r5}"


def d4_limitador_botones_en_app():
    raiz = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(raiz, "app.py"), encoding="utf-8").read()
    i = src.find('if tipo == "interactive":')
    fragmento = src[i:i + 2000] if i >= 0 else ""
    creado = "_LIMITADOR_BOTONES = Limitador(" in src
    consultado = "_LIMITADOR_BOTONES.registrar(telefono)" in fragmento
    return (creado and consultado), f"creado={creado} consultado={consultado}"


def d5_dedup_en_tres_sitios():
    raiz = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(raiz, "robot", "logic.py"), encoding="utf-8").read()
    n = src.count("if not _handoff_repetido(")
    return n >= 3, f"sitios={n}"


CASOS = [
    ("D1 doble tap en Hablar con persona = 1 correo, 2 respuestas", d1_doble_tap_un_correo),
    ("D2 dos teléfonos = dos correos", d2_dos_telefonos_dos_correos),
    ("D3 helper: repite frena, urgencia exenta, ventana expira", d3_helper_dedup),
    ("D4 botones con Limitador en app.py", d4_limitador_botones_en_app),
    ("D5 dedup en los 3 sitios de handoff", d5_dedup_en_tres_sitios),
]


def main():
    fallos = 0
    for nombre, fn in CASOS:
        limpiar()
        try:
            ok, detalle = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detalle = False, f"excepción: {exc!r}"
        estado = "PASS" if ok else "FAIL"
        if not ok:
            fallos += 1
        print(f"[{estado}] {nombre} — {detalle}")
    print(f"\n{len(CASOS) - fallos}/{len(CASOS)} casos ok (auditoría seguridad)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
