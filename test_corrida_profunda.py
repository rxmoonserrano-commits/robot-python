"""Corrida profunda (v3.20.6): adversarial sobre el código real.

Bugs encontrados en esta corrida (cada uno reproducido aquí
primero, con test permanente):

- R11: la ventana de negación (30 caracteres) dejaba pasar ofertas
  reales: "No te preocupes, te hago un descuento del 20%" y
  "Sin problema, te dejo el 2x1" se tomaban como negación honesta.
- R11: "más barato" y "meses sin intereses" no estaban cubiertos:
  promesas de dinero que pasaban el blindaje.
- R9: precios "pelados" sin $ ni pesos ("te lo dejo en 400",
  "cuesta cuatrocientos") no se detectaban.
- Urgencia: preguntas sobre el dolor ("¿el blanqueamiento causa
  dolor?", "tengo una duda sobre el dolor") disparaban el
  protocolo de urgencia en vez de una respuesta normal.
- Reporte ROI: un motivo ambiguo ("dental") cruzaba con el primer
  servicio que lo contuviera y sumaba su precio; ahora si cruza
  con precios distintos, no suma nada (nunca inventa pesos).

Uso:  python3 test_corrida_profunda.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_urgencia,
    atender_mensaje,
)
from robot.report import valor_estimado_citas  # noqa: E402
from robot.revision import (  # noqa: E402
    _montos_en_texto,
    precios_de_conocimiento,
    revisar_respuesta,
    texto_conocimiento,
)
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    CONOCIMIENTO,
    DepsDinamica,
    NOMBRE,
    TEL,
)

AHORA = AHORA_ABIERTO
PRECIOS = precios_de_conocimiento(CONOCIMIENTO)
TEXTO_CONOC = texto_conocimiento(CONOCIMIENTO)
FRASE_SEGURA = "Déjame confirmarlo con el encargado y te aviso en un momento."

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


def rev(txt, estado=None, texto_conoc=TEXTO_CONOC, precios=PRECIOS):
    return revisar_respuesta(
        txt, estado or {}, "", ahora=AHORA, telefono=TEL,
        precios_conocidos=precios, texto_conocimiento=texto_conoc)


def nuevo(clase=DepsDinamica):
    return clase(ahora=AHORA_ABIERTO)


def msg(d, texto):
    return atender_mensaje(d, TEL, NOMBRE, texto, con_ritmo=False, ahora=AHORA_ABIERTO)


def todo_texto(d):
    return " ".join(d.textos + [b[0] for b in d.botones])


# ---------------------------------------------------------------------------
# A. R11: negación lejana no debe tapar una oferta real
# ---------------------------------------------------------------------------

def a1():
    # "No te preocupes" + oferta: el "no" está a 26 caracteres del
    # "descuento", no es una negación honesta.
    t, v = rev("No te preocupes, te hago un descuento del 20% si agendamos hoy.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a2():
    t, v = rev("Sin problema, te dejo el 2x1 en la limpieza.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a3():
    t, v = rev("No te preocupes, es gratis.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a4():
    t, v = rev("Sin problema, te lo dejo gratis.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a5():
    t, v = rev("No, te hago un descuento.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a6():
    # Las negaciones honestas siguen pasando intactas.
    honestas = [
        "No manejamos descuentos, el precio es $600.",
        "Jamás damos descuentos.",
        "Descuentos no manejamos.",
        "Tampoco hacemos descuentos.",
        "No es gratis, la revisión cuesta $200.",
        "No tenemos descuentos.",
        "No ofrecemos descuentos.",
        "Sin promociones.",
        "No te preocupes, no hacemos descuentos.",
        "Nunca damos descuentos.",
    ]
    for original in honestas:
        t, v = rev(original)
        if t != original or "R11" in v:
            return False, f"honesta bloqueada: {original!r} -> {t!r} {v}"
    return True, ""


# ---------------------------------------------------------------------------
# B. R11: promesas de dinero sin la palabra "descuento"
# ---------------------------------------------------------------------------

def b1():
    t, v = rev("Te lo dejo más barato que en cualquier lado.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b2():
    # "barato" como oferta, aunque después venga un "no te preocupes".
    t, v = rev("Te sale barato, no te preocupes.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b3():
    t, v = rev("Te lo dejo a 12 meses sin intereses.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b4():
    t, v = rev("Lo puedes pagar a meses sin intereses.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b5():
    # Negaciones honestas con las palabras nuevas: pasan.
    honestas = [
        "No es barato, cuesta $600.",
        "No es sin intereses.",
    ]
    for original in honestas:
        t, v = rev(original)
        if t != original or "R11" in v:
            return False, f"honesta bloqueada: {original!r} -> {t!r} {v}"
    return True, ""


# ---------------------------------------------------------------------------
# C. R9: precios pelados (sin $ ni pesos)
# ---------------------------------------------------------------------------

def c1():
    t, v = rev("Te lo dejo en 400.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def c2():
    t, v = rev("Cuesta 400, ¿va?")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def c3():
    t, v = rev("Te lo dejo en cuatrocientos.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def c4():
    t, v = rev("El precio es cuatrocientos.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def c5():
    # Cantidades que NO son precios no deben bloquearse.
    inocentes = [
        "Son 400 pacientes al año.",
        "Te veo en 3 días.",
        "La cita es el 23 a las 9.",
        "La limpieza cuesta $600.",
        "Te sale en seiscientos pesos.",
    ]
    for original in inocentes:
        t, v = rev(original)
        if t != original or "R9" in v:
            return False, f"inocente bloqueado: {original!r} -> {t!r} {v}"
    return True, ""


def c6():
    # Extracción directa de montos.
    ok = (_montos_en_texto("cuesta 400") == [400]
          and _montos_en_texto("son 400 pacientes") == []
          and _montos_en_texto("en 3 días") == []
          and _montos_en_texto("te lo dejo en cuatrocientos.") == [400])
    return ok, f"montos={_montos_en_texto('cuesta 400')}"


# ---------------------------------------------------------------------------
# D. Urgencia: preguntas sobre el dolor no son urgencias
# ---------------------------------------------------------------------------

def d1():
    ok = _es_urgencia("¿el blanqueamiento causa dolor?") is False
    return ok, "causa dolor detectado como urgencia"


def d2():
    ok = _es_urgencia("¿el tratamiento da dolor?") is False
    return ok, "da dolor detectado como urgencia"


def d3():
    ok = _es_urgencia("tengo una duda sobre el dolor") is False
    return ok, "duda sobre el dolor detectada como urgencia"


def d4():
    # Síntomas propios: siguen siendo urgencia.
    ok = (_es_urgencia("tengo dolor de muela") is True
          and _es_urgencia("me duele la muela") is True
          and _es_urgencia("¿me duele la muela?") is True
          and _es_urgencia("no me duele nada") is False)
    return ok, "síntomas propios mal clasificados"


def d5():
    # Punta a punta: la pregunta sobre el dolor se responde normal,
    # sin handoff ni alerta urgente.
    d = nuevo()
    r = msg(d, "¿el blanqueamiento causa dolor?")
    ok = (not d.alertas_handoff and not d.alertas_urgentes
          and r.get("motivo") != "urgencia" and bool(d.textos))
    return ok, (f"handoffs={len(d.alertas_handoff)} urgentes="
                f"{len(d.alertas_urgentes)} motivo={r.get('motivo')}")


# ---------------------------------------------------------------------------
# E. Reporte ROI: motivo ambiguo no suma pesos inventados
# ---------------------------------------------------------------------------

def e1():
    # "dental" cruza con Limpieza ($600) y Blanqueamiento ($1,800):
    # sin coincidencia clara, no se suma nada.
    total, con, sin = valor_estimado_citas([{"motivo": "dental"}], CONOCIMIENTO)
    ok = (total, con, sin) == (0, 0, 1)
    return ok, f"total={total} con={con} sin={sin}"


def e2():
    # Coincidencias claras siguen sumando.
    total, con, sin = valor_estimado_citas(
        [{"motivo": "limpieza"}, {"motivo": "Limpieza dental"},
         {"motivo": "Revisión"}], CONOCIMIENTO)
    ok = (total, con, sin) == (1400, 3, 0)
    return ok, f"total={total} con={con} sin={sin}"


# ---------------------------------------------------------------------------
# F. Integración: agente "malo" que cede con negación lejana
# ---------------------------------------------------------------------------

class DepsMalo(DepsDinamica):
    """Agente falso que cede con ofertas disfrazadas de negación."""

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        ultimo = (mensaje or "").split("\n")[-1].lower()
        if "regateo" in ultimo:
            return RespuestaAgente(
                respuesta_texto="No te preocupes, te hago un descuento del 20% si agendamos hoy.")
        if "barato" in ultimo:
            return RespuestaAgente(
                respuesta_texto="Te lo dejo más barato que en cualquier lado.")
        return super().preguntar_agente(mensaje, conocimiento, fotos, historial)


def f1():
    d = nuevo(DepsMalo)
    msg(d, "regateo uno")
    texto = todo_texto(d)
    ok = ("20%" not in texto) and ("descuento" not in texto.lower()) \
        and (FRASE_SEGURA in texto)
    return ok, f"texto={texto!r}"


def f2():
    d = nuevo(DepsMalo)
    msg(d, "barato por favor")
    texto = todo_texto(d)
    ok = ("barato" not in texto.lower()) and (FRASE_SEGURA in texto)
    return ok, f"texto={texto!r}"


def main():
    for nombre, fn in [
        ("A1 'No te preocupes, te hago un descuento' se desecha (R11)", a1),
        ("A2 'Sin problema, te dejo el 2x1' se desecha (R11)", a2),
        ("A3 'No te preocupes, es gratis' se desecha (R11)", a3),
        ("A4 'Sin problema, te lo dejo gratis' se desecha (R11)", a4),
        ("A5 'No, te hago un descuento' se desecha (R11)", a5),
        ("A6 negaciones honestas pasan intactas (R11)", a6),
        ("B1 'más barato' se desecha (R11)", b1),
        ("B2 'te sale barato' se desecha (R11)", b2),
        ("B3 '12 meses sin intereses' se desecha (R11)", b3),
        ("B4 'a meses sin intereses' se desecha (R11)", b4),
        ("B5 negaciones con palabras nuevas pasan (R11)", b5),
        ("C1 'te lo dejo en 400' se desecha (R9)", c1),
        ("C2 'cuesta 400' se desecha (R9)", c2),
        ("C3 'te lo dejo en cuatrocientos' se desecha (R9)", c3),
        ("C4 'el precio es cuatrocientos' se desecha (R9)", c4),
        ("C5 cantidades inocentes pasan (R9)", c5),
        ("C6 extracción de montos pelados", c6),
        ("D1 '¿causa dolor?' no es urgencia", d1),
        ("D2 '¿da dolor?' no es urgencia", d2),
        ("D3 'duda sobre el dolor' no es urgencia", d3),
        ("D4 síntomas propios siguen siendo urgencia", d4),
        ("D5 pregunta sobre dolor se responde sin handoff", d5),
        ("E1 motivo ambiguo no suma pesos (ROI)", e1),
        ("E2 coincidencias claras siguen sumando (ROI)", e2),
        ("F1 agente que cede con negación lejana no llega al cliente", f1),
        ("F2 'más barato' del agente no llega al cliente", f2),
    ]:
        caso(nombre, fn)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok")
    if fallos:
        print("FALLARON:", ", ".join(fallos))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
