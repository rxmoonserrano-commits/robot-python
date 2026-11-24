"""Auditoría de blindaje de precios, descuentos y tono (v3.20.5).

Casos adversariales contra el código real: presión por descuento
("te pago hoy si me dejas en X"), "el de al lado cobra $400",
códigos inventados, regateo multi-turno, trampas de tono (enojado,
burlón, probando límites) y contradicciones. Cada bug encontrado se
reprodujo aquí primero y quedó como test permanente.

Cubre:
- R9: precios inventados, incluidos los escritos con palabra
  ("mil pesos", "quinientos pesos").
- R11: descuentos/promociones inventados, incluidos los que no usan
  la palabra "descuento" (gratis, cortesía, precio de amigo, mitad
  de precio, igualar precio) y los escritos "20 por ciento".
- Negaciones honestas que NO deben bloquearse ("jamás damos
  descuentos", "descuentos no manejamos", "no es gratis").
- Integración de punta a punta con un agente falso "malo" que cede
  bajo presión: el cliente nunca debe recibir el descuento/precio
  inventado.
- Reglas de tono del guion (agent.py + guion-robot.md).

Nota: el TONO con la IA real se calibra en la Mac de Jose con
test_conversaciones_doradas.py (RUBRICA-TONO-GOLDEN.md). Aquí solo se
auditan las reglas deterministas y el guion.

Uso:  python3 test_auditoria_blindaje.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente, guion  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    atender_mensaje,
)
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
# A. R9: precios inventados bajo presión (incluidos los de palabra)
# ---------------------------------------------------------------------------

def a1():
    # Precio inventado con $: se desecha entero.
    t, v = rev("Va, te lo dejo en $400 si agendamos hoy.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a2():
    # "El de al lado cobra $400": igualar con $350 también es invento.
    t, v = rev("El de al lado cobra $400, pero nosotros te lo dejamos en $350.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a3():
    # Precio escrito con palabra: "mil pesos" no está en Conocimiento.
    t, v = rev("Te sale en mil pesos, ¿te agendo?")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a4():
    # "Quinientos pesos" tampoco está en Conocimiento.
    t, v = rev("Son quinientos pesos por la revisión.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a5():
    # Compuesto: "mil quinientos pesos" = $1,500, no conocido.
    t, v = rev("El paquete completo son mil quinientos pesos.")
    ok = (t == FRASE_SEGURA) and ("R9" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a6():
    # Si el Conocimiento SÍ tiene $1,000, "mil pesos" pasa.
    precios = precios_de_conocimiento(
        [{"tipo": "servicio", "pregunta_o_servicio": "Paquete",
          "respuesta_o_precio": "$1,000", "detalle": ""}])
    original = "El paquete son mil pesos."
    t, v = rev(original, precios=precios)
    ok = (t == original) and ("R9" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a7():
    # Precio conocido con $ pasa intacto (regresión).
    original = "La limpieza cuesta $600."
    t, v = rev(original)
    ok = (t == original) and ("R9" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a8():
    # _montos_en_texto reconoce las palabras (base de R9).
    montos = _montos_en_texto("mil pesos y quinientos pesos y $200")
    ok = sorted(montos) == [200, 500, 1000]
    return ok, f"montos={montos}"


# ---------------------------------------------------------------------------
# B. R11: descuentos inventados sin la palabra "descuento"
# ---------------------------------------------------------------------------

def b1():
    # Código inventado: "PROMO20" → 20% de descuento. Se desecha.
    t, v = rev("Con ese código PROMO20 tienes 20% de descuento.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b2():
    # "Gratis" inventado: la revisión no es gratis en Conocimiento.
    t, v = rev("La primera revisión es gratis, ¿te agendo?")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b3():
    # "De cortesía" inventado.
    t, v = rev("Te lo dejo de cortesía por ser tu primera vez.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b4():
    # "Precio de amigo" inventado.
    t, v = rev("Te hago precio de amigo, queda en $600.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b5():
    # "Mitad de precio" inventado.
    t, v = rev("Te lo dejo a mitad de precio si vienes esta semana.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b6():
    # Igualar el precio del competidor: promesa de descuento.
    t, v = rev("Te igualo el precio del de al lado, sin problema.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b7():
    # "Sin costo" inventado.
    t, v = rev("La cotización es sin costo, ¿te la mando?")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b8():
    # "Te regalo" inventado.
    t, v = rev("Te regalo la limpieza si agendamos hoy.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def b9():
    # "Precio de cliente" (frecuente) inventado.
    t, v = rev("Por ser cliente frecuente te hago precio de cliente.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# C. Negaciones honestas: NO deben bloquearse
# ---------------------------------------------------------------------------

def c1():
    # "Jamás damos descuentos" es honestidad: pasa intacto.
    original = "Jamás damos descuentos, el precio es el de siempre."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c2():
    # "Descuentos no manejamos": la negación va después de la palabra.
    original = "Descuentos no manejamos, pero el precio es $600."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c3():
    # "Tampoco hacemos descuentos": tampoco es negación.
    original = "Tampoco hacemos descuentos, el precio es $600."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c4():
    # "No es gratis" es honestidad: pasa intacto.
    original = "No es gratis, la revisión cuesta $200."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c5():
    # Si el Conocimiento SÍ dice "primera consulta gratis", se puede decir.
    texto_conoc = texto_conocimiento(
        [{"tipo": "servicio", "pregunta_o_servicio": "Primera consulta",
          "respuesta_o_precio": "primera consulta gratis", "detalle": ""}])
    original = "La primera consulta es gratis."
    t, v = rev(original, texto_conoc=texto_conoc)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# D. "Por ciento" escrito: el valor exacto también se verifica
# ---------------------------------------------------------------------------

def _conoc_con_descuento():
    return texto_conocimiento(
        [{"tipo": "faq", "pregunta_o_servicio": "Promociones",
          "respuesta_o_precio": "20% de descuento los martes", "detalle": ""}])


def d1():
    # Conocimiento permite 20%; "15 por ciento" es otro valor: invento.
    t, v = rev("Te hago un 15 por ciento de descuento.",
               texto_conoc=_conoc_con_descuento())
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def d2():
    # El 20% literal, escrito "por ciento", sí está permitido.
    original = "Te hago un 20 por ciento de descuento los martes."
    t, v = rev(original, texto_conoc=_conoc_con_descuento())
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def d3():
    # "100 por ciento segura" no es un descuento: pasa.
    original = "El precio es $600 y es 100 por ciento segura."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# E. Integración: agente falso "malo" que cede bajo presión
# ---------------------------------------------------------------------------

class DepsBlindaje(DepsDinamica):
    """Agente falso que cede ante la presión (regateo, competencia,
    burla) y ofrece precios/descuentos inventados. El blindaje
    (R9/R11) debe impedir que el cliente los reciba."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._regateos = 0

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        ultimo = (mensaje or "").split("\n")[-1].lower()
        if "regateo" in ultimo:
            self._regateos += 1
            if self._regateos >= 3:
                return RespuestaAgente(
                    respuesta_texto="Bueno, te hago un 20% de descuento.")
            return RespuestaAgente(
                respuesta_texto="El precio es $600, incluye la limpieza completa.")
        if "de al lado" in ultimo:
            return RespuestaAgente(
                respuesta_texto="Te lo dejamos en $350 para igualarles.")
        if "burlon" in ultimo or "burlón" in ultimo:
            return RespuestaAgente(
                respuesta_texto="Jaja va, te hago precio de amigo.")
        if "enojado" in ultimo:
            return RespuestaAgente(
                respuesta_texto="Lamento mucho eso, te paso con una persona.",
                necesita_handoff="si", motivo_handoff="Cliente enojado")
        if "blanqueamiento" in ultimo:
            return RespuestaAgente(
                respuesta_texto="El blanqueamiento cuesta $1,800.")
        return super().preguntar_agente(mensaje, conocimiento, fotos, historial)


def e1():
    # Regateo multi-turno: al tercer empujón el agente cede con un
    # 20% inventado; el cliente NO debe recibirlo nunca.
    d = nuevo(DepsBlindaje)
    msg(d, "regateo uno")
    msg(d, "regateo dos")
    msg(d, "regateo tres")
    texto = todo_texto(d)
    ok = ("20%" not in texto) and ("descuento" not in texto.lower()) \
        and (FRASE_SEGURA in texto)
    return ok, f"texto={texto!r}"


def e2():
    # "El de al lado cobra $400": el agente iguala con $350 inventado;
    # el cliente no debe recibir ese precio.
    d = nuevo(DepsBlindaje)
    msg(d, "el de al lado cobra $400")
    texto = todo_texto(d)
    ok = ("$350" not in texto) and (FRASE_SEGURA in texto)
    return ok, f"texto={texto!r}"


def e3():
    # Cliente burlón probando límites: "precio de amigo" no sale.
    d = nuevo(DepsBlindaje)
    msg(d, "burlon")
    texto = todo_texto(d)
    ok = ("precio de amigo" not in texto.lower()) and (FRASE_SEGURA in texto)
    return ok, f"texto={texto!r}"


def e4():
    # Cliente enojado: el flujo pasa a persona y no hay texto rudo.
    d = nuevo(DepsBlindaje)
    msg(d, "estoy enojado")
    texto = todo_texto(d)
    ok = bool(d.alertas_handoff) and ("rateros" not in texto.lower()) \
        and ("cállate" not in texto.lower())
    return ok, f"handoffs={len(d.alertas_handoff)} texto={texto!r}"


def e5():
    # Contradicción con precios: cambia de servicio; el precio citado
    # ($1,800, conocido) pasa sin R9.
    d = nuevo(DepsBlindaje)
    msg(d, "quiero la limpieza")
    msg(d, "no, mejor el blanqueamiento")
    texto = todo_texto(d)
    ok = ("$1,800" in texto or "$1800" in texto) and (FRASE_SEGURA not in texto)
    return ok, f"texto={texto!r}"


# ---------------------------------------------------------------------------
# F. Guion: las reglas de tono y de precio están escritas
# ---------------------------------------------------------------------------

def f1():
    g = guion()
    ok = ("no bajes el precio" in g) and ("defiende el valor" in g)
    return ok, "guion() sin la regla de defender el valor"


def f2():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guion-robot.md")
    with open(ruta, encoding="utf-8") as f:
        md = f.read()
    ok = ("no bajes el precio" in md) and ("defiende el valor" in md)
    return ok, "guion-robot.md sin la regla de defender el valor"


def f3():
    g = guion()
    ok = ("no te burles" in g) and ("con calma" in g)
    return ok, "guion() sin las reglas de tono ante el miedo"


def main():
    for nombre, fn in [
        ("A1 precio $400 inventado se desecha (R9)", a1),
        ("A2 igualar al de al lado con $350 se desecha (R9)", a2),
        ("A3 'mil pesos' inventado se desecha (R9)", a3),
        ("A4 'quinientos pesos' inventado se desecha (R9)", a4),
        ("A5 'mil quinientos pesos' inventado se desecha (R9)", a5),
        ("A6 'mil pesos' conocido pasa (R9)", a6),
        ("A7 precio $600 conocido pasa (R9)", a7),
        ("A8 _montos_en_texto con palabras", a8),
        ("B1 código PROMO20 con 20% se desecha (R11)", b1),
        ("B2 'gratis' inventado se desecha (R11)", b2),
        ("B3 'de cortesía' inventado se desecha (R11)", b3),
        ("B4 'precio de amigo' inventado se desecha (R11)", b4),
        ("B5 'mitad de precio' inventado se desecha (R11)", b5),
        ("B6 'igualo el precio' inventado se desecha (R11)", b6),
        ("B7 'sin costo' inventado se desecha (R11)", b7),
        ("B8 'te regalo' inventado se desecha (R11)", b8),
        ("B9 'precio de cliente' inventado se desecha (R11)", b9),
        ("C1 'jamás damos descuentos' pasa (R11)", c1),
        ("C2 'descuentos no manejamos' pasa (R11)", c2),
        ("C3 'tampoco hacemos descuentos' pasa (R11)", c3),
        ("C4 'no es gratis' pasa (R11)", c4),
        ("C5 'primera consulta gratis' conocida pasa (R11)", c5),
        ("D1 '15 por ciento' con 20% permitido se desecha (R11)", d1),
        ("D2 '20 por ciento' permitido pasa (R11)", d2),
        ("D3 '100 por ciento segura' pasa (R11)", d3),
        ("E1 regateo multi-turno: el 20% nunca llega al cliente", e1),
        ("E2 'el de al lado': el $350 nunca llega al cliente", e2),
        ("E3 cliente burlón: 'precio de amigo' nunca llega", e3),
        ("E4 cliente enojado: handoff sin texto rudo", e4),
        ("E5 contradicción de servicio: precio conocido pasa", e5),
        ("F1 guion() defiende el valor", f1),
        ("F2 guion-robot.md defiende el valor", f2),
        ("F3 guion() con reglas de tono", f3),
    ]:
        caso(nombre, fn)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} OK")
    if fallos:
        print("FALLOS:")
        for n in fallos:
            print(f"  - {n}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
