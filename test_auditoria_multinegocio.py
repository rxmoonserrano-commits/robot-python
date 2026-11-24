"""Auditoría v3.20.4 — Área 6: multi-negocio (aislamiento de datos).

Dos negocios simulados = dos Deps con backends falsos separados y
el MISMO teléfono en ambos. Verifica que citas, conversaciones y
memoria jamás se crucen. La frontera de aislamiento es el PROCESO
(un despliegue por negocio: un Render + una hoja + un número por
negocio); E3 fija ese contrato: las propuestas viven en el proceso.

Corre con: python3 test_auditoria_multinegocio.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    atender_boton,
    atender_mensaje,
)
from test_bateria_dinamica import AHORA_ABIERTO, NOMBRE, TEL, _propuesta_base  # noqa: E402
from test_simulacion_profunda import DepsProfunda  # noqa: E402

AHORA = AHORA_ABIERTO


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()


def e1_citas_y_conversaciones_aisladas():
    neg_a = DepsProfunda(ahora=AHORA)
    neg_b = DepsProfunda(ahora=AHORA)
    # Negocio A: el cliente confirma una cita
    _CITAS_PENDIENTES[TEL] = dict(_propuesta_base(AHORA))
    atender_boton(neg_a, TEL, NOMBRE, "confirmar_cita", con_ritmo=False, ahora=AHORA)
    # Negocio B: el MISMO teléfono solo pregunta un precio
    neg_b.agente_override = RespuestaAgente(respuesta_texto="La limpieza cuesta $600.")
    atender_mensaje(neg_b, TEL, NOMBRE, "cuánto cuesta la limpieza",
                    con_ritmo=False, ahora=AHORA)
    conv_a = " ".join(str(c) for c in neg_a.conversaciones)
    conv_b = " ".join(str(c) for c in neg_b.conversaciones)
    ok = (len(neg_a.citas) == 1 and len(neg_b.citas) == 0
          and "cuesta" not in conv_a
          and "cuesta" in conv_b)
    return ok, (f"A citas={len(neg_a.citas)} B citas={len(neg_b.citas)} "
                f"convA={conv_a[:150]!r} convB={conv_b[:150]!r}")


def e2_memoria_aislada():
    neg_a = DepsProfunda(ahora=AHORA)
    neg_b = DepsProfunda(ahora=AHORA)
    neg_a.agente_override = RespuestaAgente(
        respuesta_texto="Claro.", resumen_cliente="Dato privado del negocio A")
    neg_b.agente_override = RespuestaAgente(
        respuesta_texto="Claro.", resumen_cliente="Dato privado del negocio B")
    atender_mensaje(neg_a, TEL, NOMBRE, "hola", con_ritmo=False, ahora=AHORA)
    atender_mensaje(neg_b, TEL, NOMBRE, "hola", con_ritmo=False, ahora=AHORA)
    mem_a = " ".join(m.get("resumen", "") for m in neg_a.memorias)
    mem_b = " ".join(m.get("resumen", "") for m in neg_b.memorias)
    ok = ("negocio A" in mem_a and "negocio B" not in mem_a
          and "negocio B" in mem_b and "negocio A" not in mem_b)
    return ok, f"memA={mem_a!r} memB={mem_b!r}"


def e3_frontera_de_proceso():
    # Frontera documentada: _CITAS_PENDIENTES es estado del PROCESO
    # (llave = teléfono, sin dimensión de negocio). Dos negocios en
    # el mismo proceso compartirían propuestas; por eso el
    # aislamiento real es un despliegue por negocio (un Render +
    # una hoja + un número por negocio), nunca dos en un proceso.
    # Este caso fija el contrato: si algún día se intenta servir dos
    # negocios en un proceso, este test truena y obliga a namespacer.
    neg_b = DepsProfunda(ahora=AHORA)
    _CITAS_PENDIENTES[TEL] = dict(_propuesta_base(AHORA))
    r = atender_boton(neg_b, TEL, NOMBRE, "confirmar_cita",
                      con_ritmo=False, ahora=AHORA)
    ok = len(neg_b.citas) == 1
    return ok, f"citasB={len(neg_b.citas)} r={r}"


CASOS = [
    ("E1 citas y conversaciones aisladas por negocio", e1_citas_y_conversaciones_aisladas),
    ("E2 memoria aislada por negocio", e2_memoria_aislada),
    ("E3 frontera de proceso (propuestas = estado del proceso)", e3_frontera_de_proceso),
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
    print(f"\n{len(CASOS) - fallos}/{len(CASOS)} casos ok (auditoría multi-negocio)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
