"""Corrida adversarial profunda (v3.20.1): barrida propia sobre el código real.

Sondas nuevas sobre los clasificadores puros (_es_confirmacion_asistencia,
_extraer_telefono, _es_urgencia, _intencion_cambio, _es_afirmacion) y sobre
el flujo real con el harness de test_bateria_dinamica. Cada sonda que
rompe una invariante se reporta con el caso exacto.

Uso:  python3 test_corrida_adversarial.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_afirmacion,
    _es_confirmacion_asistencia,
    _es_urgencia,
    _extraer_telefono,
    _intencion_cambio,
    atender_boton,
    atender_mensaje,
)
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    DepsDinamica,
    H2,
    NOMBRE,
    TEL,
    _fila_espejo,
    _propuesta_base,
)

RESULTADOS = []


def limpiar():
    _CITAS_PENDIENTES.clear()
    _RETOMAR.clear()
    _BAJA_CONFIANZA.clear()


def caso(nombre, fn):
    limpiar()
    try:
        ok, detalle = fn()
    except Exception as exc:
        ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok))
    marca = "PASS" if ok else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not ok else ""))
    limpiar()


def nuevo(espejo=None, historial=None, cliente=None, propuesta=None,
          ahora=AHORA_ABIERTO):
    d = DepsDinamica(espejo=espejo, historial=historial, cliente=cliente,
                     ahora=ahora)
    if propuesta is not None:
        _CITAS_PENDIENTES[TEL] = dict(propuesta)
    return d


def msg(d, texto, ahora=AHORA_ABIERTO):
    return atender_mensaje(d, TEL, NOMBRE, texto, con_ritmo=False, ahora=ahora)


def btn(d, boton_id, ahora=AHORA_ABIERTO):
    return atender_boton(d, TEL, NOMBRE, boton_id, con_ritmo=False, ahora=ahora)


def todo_texto(d):
    return " ".join(d.textos + [b[0] for b in d.botones])


# ---------------------------------------------------------------------------
# A. Confirmación de asistencia: falsos positivos
# ---------------------------------------------------------------------------

def a1():
    # "confirmo que no podré ir" NO es confirmar asistencia.
    r = _es_confirmacion_asistencia("confirmo que no podré ir")
    return (not r), f"_es_confirmacion_asistencia('confirmo que no podré ir')={r}"


def a2():
    # "confirmo pero quiero cambiar" NO es confirmar asistencia pura.
    r = _es_confirmacion_asistencia("confirmo, pero quiero cambiar la cita")
    return (not r), f"_es_confirmacion_asistencia('confirmo, pero quiero cambiar...')={r}"


def a3():
    # "ya no nos vemos el martes" NO es confirmar asistencia.
    r = _es_confirmacion_asistencia("ya no nos vemos el martes")
    return (not r), f"_es_confirmacion_asistencia('ya no nos vemos el martes')={r}"


def a4():
    # Integración: cliente con cita futura dice "confirmo que no podré ir":
    # NO debe registrar confirmación de asistencia ni responder "quedó confirmada".
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2, "motivo": "Blanqueamiento dental",
           "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cli)
    msg(d, "confirmo que no podré ir")
    ok = (not d.actualizaciones) and ("confirmada tu asistencia" not in todo_texto(d))
    return ok, f"textos={d.textos} actualizaciones={d.actualizaciones}"


def a5():
    # Integración: "confirmo pero quiero cambiar" con cita futura: el
    # cambio debe atenderse (no tragarse la confirmación).
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2, "motivo": "Blanqueamiento dental",
           "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cli)
    r = msg(d, "confirmo pero quiero cambiar la cita")
    ok = (not r.get("confirmacion_asistencia")) and bool(d.textos)
    return ok, f"r={r} textos={d.textos}"


def a6():
    # Los sí de verdad siguen funcionando.
    ok = (_es_confirmacion_asistencia("confirmo")
          and _es_confirmacion_asistencia("ahí nos vemos")
          and _es_confirmacion_asistencia("confirmado"))
    return ok, "confirmación de asistencia legítima dejó de funcionar"


# ---------------------------------------------------------------------------
# B. _extraer_telefono: fechas/horas no son teléfonos
# ---------------------------------------------------------------------------

def b1():
    r = _extraer_telefono("sí, el 2026-11-23 a las 10", TEL)
    return (r == ""), f"_extraer_telefono('sí, el 2026-11-23 a las 10')={r!r}"


def b2():
    r = _extraer_telefono("regístralo al 6671234567", TEL)
    return (r != ""), f"_extraer_telefono('regístralo al 6671234567')={r!r}"


def b3():
    r = _extraer_telefono("mi número es 669 123 4567", TEL)
    return (r != ""), f"_extraer_telefono('mi número es 669 123 4567')={r!r}"


def b4():
    # Un número de 8 dígitos (fecha corta) no es teléfono.
    r = _extraer_telefono("el 23 de noviembre", TEL)
    return (r == ""), f"_extraer_telefono('el 23 de noviembre')={r!r}"


# ---------------------------------------------------------------------------
# C. Urgencia: frases reales que faltan / falsos positivos
# ---------------------------------------------------------------------------

def c1():
    # "me urge" a secas es ambiguo ("me urge saber el precio"): por
    # diseño NO dispara el protocolo; va al agente. Solo con una
    # señal médica clara ("me duele") es urgencia. (La batería
    # dinámica lo clasifica como falso_sí: no debe confirmar.)
    r = _es_urgencia("me urge una cita")
    r2 = _es_urgencia("me urge una cita, me duele la muela")
    ok = (not r) and r2
    return ok, f"'me urge una cita'={r} (esperado False), con dolor={r2} (esperado True)"


def c2():
    # "no tengo dolor" NO es urgencia.
    r = _es_urgencia("no tengo dolor, solo quiero una limpieza")
    return (not r), f"_es_urgencia('no tengo dolor...')={r}"


def c3():
    # "sangro mucho" es urgencia.
    r = _es_urgencia("sangro mucho desde ayer")
    return r, f"_es_urgencia('sangro mucho desde ayer')={r}"


def c4():
    # "se me hinchó la cara" es urgencia.
    r = _es_urgencia("se me hinchó la cara")
    return r, f"_es_urgencia('se me hinchó la cara')={r}"


def c5():
    # Las negaciones y preguntas siguen sin ser urgencia.
    ok = (not _es_urgencia("no me duele nada"))
    ok = ok and (not _es_urgencia("¿duele la limpieza?"))
    ok = ok and (not _es_urgencia("es urgente que me digas el precio"))
    return ok, "una no-urgencia disparó el protocolo"


# ---------------------------------------------------------------------------
# D. Cambiar/cancelar: no tocar lo que el cliente no pidió
# ---------------------------------------------------------------------------

def d1():
    # "cancela la de mi vecino" no debe cancelar la cita del cliente.
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cliente = {"estatus": "agendado", "fecha_cita": H2,
               "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cliente)
    r = msg(d, "cancela la de mi vecino, no la mía")
    ok = (not r.get("cita_cancelada")) and (not d.citas_canceladas)
    return ok, f"r={r} canceladas={d.citas_canceladas} textos={d.textos}"


def d2():
    # "no quiero la cita" es cancelar, no cambiar.
    r = _intencion_cambio("no quiero la cita")
    return (r == "cancelar"), f"_intencion_cambio('no quiero la cita')={r!r}"


def d3():
    # "no quiero esa hora" sigue siendo cambiar (no cancelar).
    r = _intencion_cambio("no quiero esa hora, ¿tienen otra?")
    return (r == "cambiar"), f"_intencion_cambio('no quiero esa hora...')={r!r}"


def d4():
    # "cancelar" con solo propuesta pendiente: la propuesta se borra y
    # el cliente recibe confirmación de cancelación, no una pregunta
    # de "qué día te viene mejor" como si quisiera cambiar.
    d = nuevo(propuesta=_propuesta_base(AHORA_ABIERTO))
    r = msg(d, "cancelar")
    ok = (TEL not in _CITAS_PENDIENTES) and bool(d.textos)
    detalle = f"r={r} textos={d.textos} propuesta={_CITAS_PENDIENTES.get(TEL)}"
    return ok, detalle


# ---------------------------------------------------------------------------
# E. Afirmación: falsos sí
# ---------------------------------------------------------------------------

def e1():
    # "sí, pero no sé" no confirma.
    r = _es_afirmacion("sí, pero no sé")
    return (not r), f"_es_afirmacion('sí, pero no sé')={r}"


def e2():
    # "ok, no" no confirma.
    r = _es_afirmacion("ok, no")
    return (not r), f"_es_afirmacion('ok, no')={r}"


def e3():
    # "ya" solo, con propuesta: ¿confirma? (sonda informativa)
    r = _es_afirmacion("ya")
    return True, f"_es_afirmacion('ya')={r} (informativo)"


# ---------------------------------------------------------------------------
# F. Sondas extra (impacto real y variantes)
# ---------------------------------------------------------------------------

def f1():
    # Impacto real de C2: "no tengo dolor" NO debe disparar handoff
    # de urgencia ni propuesta urgente.
    d = nuevo()
    r = msg(d, "no tengo dolor, solo quiero una limpieza")
    ok = (not d.alertas_handoff) and (not d.alertas_urgentes)
    return ok, f"r={r} handoff={d.alertas_handoff} urgentes={d.alertas_urgentes}"


def f2():
    # "cambia la cita de mi hermana" con cita propia: no debe tocar
    # la cita del cliente (ni cancelar ni cambiar la suya).
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2, "motivo": "Blanqueamiento dental",
           "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cli)
    r = msg(d, "cambia la cita de mi hermana")
    ok = (not r.get("cita_cancelada")) and (not d.citas_canceladas)
    return ok, f"r={r} canceladas={d.citas_canceladas} textos={d.textos}"


def f3():
    # "cancelar" con solo propuesta: el cliente debe recibir una
    # confirmación de cancelación, no una pregunta de "qué día te
    # viene mejor" como si quisiera cambiar.
    d = nuevo(propuesta=_propuesta_base(AHORA_ABIERTO))
    r = msg(d, "cancelar")
    texto = todo_texto(d).lower()
    ok = (TEL not in _CITAS_PENDIENTES) and ("cancel" in texto)
    return ok, f"textos={d.textos} propuesta={_CITAS_PENDIENTES.get(TEL)}"


def main():
    caso("A1 'confirmo que no podré ir' no es confirmación", a1)
    caso("A2 'confirmo pero quiero cambiar' no es confirmación", a2)
    caso("A3 'ya no nos vemos el martes' no es confirmación", a3)
    caso("A4 integración: 'confirmo que no podré ir' no registra asistencia", a4)
    caso("A5 integración: 'confirmo pero quiero cambiar' atiende el cambio", a5)
    caso("A6 confirmaciones legítimas siguen funcionando", a6)
    caso("B1 fecha+hora no se extrae como teléfono", b1)
    caso("B2 teléfono real sí se extrae", b2)
    caso("B3 teléfono con espacios sí se extrae", b3)
    caso("B4 'el 23 de noviembre' no es teléfono", b4)
    caso("C1 'me urge' + dolor es urgencia", c1)
    caso("C2 'no tengo dolor' no es urgencia", c2)
    caso("C3 'sangro mucho' es urgencia", c3)
    caso("C4 'se me hinchó la cara' es urgencia", c4)
    caso("C5 negaciones/preguntas no son urgencia", c5)
    caso("D1 'cancela la de mi vecino' no cancela la propia", d1)
    caso("D2 'no quiero la cita' es cancelar", d2)
    caso("D3 'no quiero esa hora' es cambiar", d3)
    caso("D4 'cancelar' con solo propuesta borra la propuesta", d4)
    caso("E1 'sí, pero no sé' no confirma", e1)
    caso("E2 'ok, no' no confirma", e2)
    caso("E3 sonda 'ya' (informativo)", e3)
    caso("F1 'no tengo dolor' no dispara handoff de urgencia", f1)
    caso("F2 'cambia la cita de mi hermana' no toca la propia", f2)
    caso("F3 'cancelar' con propuesta confirma cancelación", f3)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok "
          f"(corrida adversarial)")
    if fallos:
        print("Fallos:")
        for n in fallos:
            print(f"  - {n}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
