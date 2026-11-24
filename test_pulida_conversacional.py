"""Pulida conversacional (v3.20.2): clientes emocionales y difíciles,
descuentos inventados, robot-speak y errores de dedo.

Cubre los encargos de la pulida profunda del motor conversacional:
- Revisor R11 (ningún descuento inventado), R12 (fuera el
  robot-speak de "pendientes") y R13 (no re-preguntar lo mismo
  tras un "ok"), más la oferta verbal "te propongo".
- Errores de dedo fuertes en cancelar/cambiar ("canselo", "canbiar").
- Quejas delicadas en la red de seguridad (_es_queja).
- El guion nuevo: miedo/fobia, cliente triste, queja delicada,
  pedidos fuera de lo normal, contradicción entre mensajes, miedos
  en la memoria.
- Integración con el harness de test_bateria_dinamica: miedo,
  queja delicada con handoff, pedidos fuera de lo normal,
  descuento inventado atrapado de punta a punta, re-pregunta
  atrapada de punta a punta, cancelación con error de dedo,
  mensajes contradictorios, dolor a las 3 am, cliente enojado.

Uso:  python3 test_pulida_conversacional.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robot.agent import RespuestaAgente, guion  # noqa: E402
from robot.estado import estado_cliente  # noqa: E402
from robot.logic import (  # noqa: E402
    _BAJA_CONFIANZA,
    _CITAS_PENDIENTES,
    _RETOMAR,
    _es_queja,
    _intencion_cambio,
    atender_mensaje,
)
from robot.revision import (  # noqa: E402
    _es_oferta,
    precios_de_conocimiento,
    revisar_respuesta,
    texto_conocimiento,
)
from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    AHORA_CERRADO,
    CONOCIMIENTO,
    DepsDinamica,
    H2,
    NOMBRE,
    TEL,
    _fila_espejo,
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


def rev(txt, estado=None, texto_conoc=TEXTO_CONOC):
    return revisar_respuesta(
        txt, estado or {}, "", ahora=AHORA, telefono=TEL,
        precios_conocidos=PRECIOS, texto_conocimiento=texto_conoc)


def nuevo(clase=DepsDinamica, espejo=None, historial=None, cliente=None,
          propuesta=None, ahora=AHORA_ABIERTO):
    d = clase(espejo=espejo, historial=historial, cliente=cliente, ahora=ahora)
    if propuesta is not None:
        _CITAS_PENDIENTES[TEL] = dict(propuesta)
    return d


def msg(d, texto, ahora=AHORA_ABIERTO):
    return atender_mensaje(d, TEL, NOMBRE, texto, con_ritmo=False, ahora=ahora)


def todo_texto(d):
    return " ".join(d.textos + [b[0] for b in d.botones])


class DepsPulida(DepsDinamica):
    """DepsDinamica con un agente falso que entiende los casos de la
    pulida: quejas delicadas, pedidos fuera de lo normal, descuentos
    inventados y re-preguntas. Los demás casos delegan al clasificador
    de la batería dinámica."""

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        ultimo = (mensaje or "").split("\n")[-1].lower()
        # Queja delicada: el agente pasa a una persona.
        if any(p in ultimo for p in (
            "no me gustó", "no me gusto", "quedé inconforme", "quede inconforme",
            "me atendieron mal", "me dolió mucho después", "me dolio mucho despues",
            "salí peor", "sali peor",
        )):
            return RespuestaAgente(
                respuesta_texto="Lamento mucho eso, te paso con una persona para que lo vea.",
                necesita_handoff="si", motivo_handoff="Queja delicada")
        # Cliente enojado: pasa a una persona.
        if any(p in ultimo for p in ("burla", "me cansé", "me canse")):
            return RespuestaAgente(
                respuesta_texto="Entiendo tu enojo, te paso con una persona.",
                necesita_handoff="si", motivo_handoff="Cliente enojado")
        # Pedido fuera de lo normal: no se inventa, se confirma con el encargado.
        if any(p in ultimo for p in (
            "en mi casa", "trueque", "traigo a 5", "descuento por grupo",
        )):
            return RespuestaAgente(
                respuesta_texto=FRASE_SEGURA,
                necesita_handoff="si", motivo_handoff="Pedido fuera de lo normal")
        # Descuento inventado (para probar R11 de punta a punta): el
        # agente "malo" ofrece un descuento que no está en Conocimiento.
        if "quiero descuento" in ultimo:
            return RespuestaAgente(
                respuesta_texto="Te hago un 20% de descuento si agendamos hoy.")
        # Re-pregunta tras un "ok" (para probar R13 de punta a punta).
        if ultimo.strip() == "ok":
            return RespuestaAgente(respuesta_texto="¿Cuál servicio te interesa?")
        # Miedo: respuesta cálida (el guion nuevo la pide; aquí solo se
        # verifica que el flujo la deja pasar sin crear citas).
        if any(p in ultimo for p in ("miedo", "pavor", "cucarachas")):
            return RespuestaAgente(
                respuesta_texto="Tranquilo, sin dolor. Te atiendo con calma.")
        return super().preguntar_agente(mensaje, conocimiento, fotos, historial)


# ---------------------------------------------------------------------------
# A. R11: ningún descuento ni promoción inventada
# ---------------------------------------------------------------------------

def a1():
    # "Te hago un 20% de descuento" no está en Conocimiento: R11 lo desecha.
    t, v = rev("Te hago un 20% de descuento si agendamos hoy.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a2():
    # Promoción inventada también se desecha.
    t, v = rev("Te aplico una promoción especial del 2x1.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a3():
    # "No manejamos descuentos" es honestidad: pasa intacto.
    original = "No manejamos descuentos, pero el precio es el de siempre."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a4():
    # "Sin descuentos, el precio es $600" también es honesto: pasa.
    original = "Sin descuentos, el precio es $600."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a5():
    # Si el Conocimiento SÍ habla de descuentos, la IA puede mencionarlos.
    texto_conoc = texto_conocimiento(
        [{"tipo": "faq", "pregunta_o_servicio": "Promociones",
          "respuesta_o_precio": "10% de descuento los martes", "detalle": ""}])
    original = "Te hago un 10% de descuento los martes."
    t, v = rev(original, texto_conoc=texto_conoc)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a6():
    # "Precio especial" inventado también se desecha.
    t, v = rev("Te hago un precio especial.")
    ok = (t == FRASE_SEGURA) and ("R11" in v)
    return ok, f"texto={t!r} violaciones={v}"


def a7():
    # El "100%" de énfasis no es un descuento: pasa.
    original = "El precio es $600 y es 100% segura."
    t, v = rev(original)
    ok = (t == original) and ("R11" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def a8():
    # Sin texto del Conocimiento, R11 no se aplica (compatibilidad).
    t, v = rev("Te hago un 20% de descuento.", texto_conoc="")
    ok = ("R11" not in v) and ("descuento" in t)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# B. R12: fuera el robot-speak de "pendientes"
# ---------------------------------------------------------------------------

def b1():
    # "Quedamos en tus pendientes" se limpia y queda el resto.
    t, v = rev("Quedamos en tus pendientes, ¿te agendo para mañana?")
    ok = ("pendientes" not in t) and ("R12" in v) and ("te agendo" in t)
    return ok, f"texto={t!r} violaciones={v}"


def b2():
    # "Pendiente" en singular ("quedó pendiente tu cita") no se toca.
    original = "Quedó pendiente tu cita del martes."
    t, v = rev(original)
    ok = (t == original) and ("R12" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def b3():
    # Si la respuesta ERA solo la frase de pendientes, pregunta neutra.
    t, v = rev("Tus pendientes.")
    ok = (t == "¿Te ayudo con algo más?") and ("R12" in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# C. R13: no re-preguntar lo mismo tras un "ok"
# ---------------------------------------------------------------------------

def c1():
    # Tras un "ok", re-preguntar casi lo mismo se reemplaza.
    estado = {
        "ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele. ¿Cuál te interesa?",
        "ultimo_mensaje_cliente": "ok",
    }
    t, v = rev("¿Cuál servicio te interesa?", estado)
    ok = (t == "¿Te ayudo con algo más?") and ("R13" in v)
    return ok, f"texto={t!r} violaciones={v}"


def c2():
    # Si el cliente REPITIÓ su pregunta, re-contestar parecido es
    # legítimo: no se toca.
    estado = {
        "ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele. ¿Cuál te interesa?",
        "ultimo_mensaje_cliente": "¿cuánto cuesta la limpieza?",
    }
    original = "¿Cuál servicio te interesa?"
    t, v = rev(original, estado)
    ok = (t == original) and ("R13" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c3():
    # Re-contestar con datos nuevos (precio + pregunta distinta) no
    # es repetir: el embudo sigue.
    estado = {
        "ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele. ¿Cuál te interesa?",
        "ultimo_mensaje_cliente": "ok",
    }
    original = "La limpieza cuesta $600 y no duele. ¿Quieres que te agende una?"
    t, v = rev(original, estado)
    ok = (t == original) and ("R13" not in v)
    return ok, f"texto={t!r} violaciones={v}"


def c4():
    # La repetición exacta sigue siendo R10 (regresión).
    estado = {
        "ultimo_mensaje_robot": "La limpieza cuesta $600 y no duele. ¿Cuál te interesa?",
        "ultimo_mensaje_cliente": "ok",
    }
    t, v = rev("La limpieza cuesta $600 y no duele. ¿Cuál te interesa?", estado)
    ok = (t == "¿Te ayudo con algo más?") and ("R10" in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# D. "Te propongo" es una oferta verbal
# ---------------------------------------------------------------------------

def d1():
    r = _es_oferta("Te propongo tu cita para el martes a las 9:00.")
    return r, f"_es_oferta('Te propongo tu cita...')={r}"


def d2():
    r = _es_oferta("Te propongo que lo pienses con calma.")
    return (not r), f"_es_oferta('Te propongo que lo pienses...')={r}"


def d3():
    r = _es_oferta("Te propongo el martes a las 09:00 con la Dra. Ruiz.")
    return r, f"_es_oferta('Te propongo el martes...')={r}"


def d4():
    # El estado detecta la oferta verbal "te propongo".
    historial = [
        {"quien_hablo": "robot", "mensaje": "Te propongo tu cita para el martes a las 9:00."},
        {"quien_hablo": "cliente", "mensaje": "ok"},
    ]
    est = estado_cliente(historial, None, {}, NOMBRE, ahora=AHORA)
    return est["ya_ofrecio_cita"], f"ya_ofrecio_cita={est['ya_ofrecio_cita']}"


def d5():
    # En un saludo, la oferta "te propongo" se quita (R2).
    t, v = rev("Te propongo tu cita para el martes a las 9:00.",
               {"etapa": "saludo"})
    ok = ("propongo" not in t) and ("R2" in v)
    return ok, f"texto={t!r} violaciones={v}"


# ---------------------------------------------------------------------------
# E. Errores de dedo en cancelar/cambiar
# ---------------------------------------------------------------------------

def e1():
    r = _intencion_cambio("canselo mi cita")
    return (r == "cancelar"), f"_intencion_cambio('canselo mi cita')={r!r}"


def e2():
    r = _intencion_cambio("cansela la cita")
    return (r == "cancelar"), f"_intencion_cambio('cansela la cita')={r!r}"


def e3():
    r = _intencion_cambio("cancelo mi cita")
    return (r == "cancelar"), f"_intencion_cambio('cancelo mi cita')={r!r}"


def e4():
    r = _intencion_cambio("anulo mi cita")
    return (r == "cancelar"), f"_intencion_cambio('anulo mi cita')={r!r}"


def e5():
    r = _intencion_cambio("canbiar la cita")
    return (r == "cambiar"), f"_intencion_cambio('canbiar la cita')={r!r}"


def e6():
    r = _intencion_cambio("cambair la cita")
    return (r == "cambiar"), f"_intencion_cambio('cambair la cita')={r!r}"


def e7():
    # Las negaciones de las variantes con error de dedo no cancelan.
    ok = (_intencion_cambio("no canselo mi cita") is None
          and _intencion_cambio("no canbiar la cita") is None
          and _intencion_cambio("no cancelo, mejor déjala") is None)
    return ok, "una negación con error de dedo disparó la mecánica"


def e8():
    # Regresiones: los mensajes bien escritos siguen funcionando.
    ok = (_intencion_cambio("cancelar mi cita") == "cancelar"
          and _intencion_cambio("mejor no, quiero cambiarla") == "cambiar"
          and _intencion_cambio("no quiero cancelar") is None)
    return ok, "una regresión en _intencion_cambio"


# ---------------------------------------------------------------------------
# F. Quejas delicadas (red de seguridad, robot apagado)
# ---------------------------------------------------------------------------

def f1():
    ok = _es_queja("no me gustó la cita pasada")
    return ok, "_es_queja('no me gustó la cita pasada')=False"


def f2():
    ok = (_es_queja("quedé inconforme con la atención")
          and _es_queja("me atendieron mal la vez pasada")
          and _es_queja("salí peor de como entré"))
    return ok, "alguna queja delicada no se detectó"


def f3():
    ok = _es_queja("después de la cita me dolió mucho")
    return ok, "_es_queja('después de la cita me dolió mucho')=False"


def f4():
    # Mensajes normales no son quejas.
    ok = (not _es_queja("¿cuánto cuesta la limpieza?"))
    ok = ok and (not _es_queja("quiero agendar una cita"))
    ok = ok and (not _es_queja("me duele la muela"))
    return ok, "un mensaje normal se tomó como queja"


# ---------------------------------------------------------------------------
# G. El guion nuevo (agent.py y guion-robot.md sincronizados)
# ---------------------------------------------------------------------------

def g1():
    g = guion()
    ok = ("Miedo o fobia" in g and "Queja delicada" in g
          and "fuera de lo normal" in g and "ÚLTIMO que" in g
          and "miedos o" in g)
    return ok, "falta alguna entrada nueva en el guion de agent.py"


def g2():
    texto = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "guion-robot.md"), encoding="utf-8").read()
    ok = ("Miedo o fobia" in texto and "Queja delicada" in texto
          and "fuera de lo normal" in texto)
    return ok, "guion-robot.md no está sincronizado con el guion"


# ---------------------------------------------------------------------------
# H. Integración: clientes emocionales y difíciles
# ---------------------------------------------------------------------------

def h1():
    # Miedo ("me dan miedo las cucarachas"): responde cálido, sin
    # crear citas ni pasar a una persona a la fuerza.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "me dan miedo las cucarachas")
    ok = (r.get("respondio") and "Tranquilo" in todo_texto(d)
          and not d.citas and not d.botones and not r.get("handoff"))
    return ok, f"r={r} textos={d.textos} botones={d.botones}"


def h2():
    # Queja delicada: pasa a una persona con correo al dueño.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "no me gustó la cita pasada, me dolió mucho después")
    ok = (r.get("handoff") and d.alertas_handoff and not d.citas)
    return ok, f"r={r} alertas={d.alertas_handoff} textos={d.textos}"


def h3():
    # Pedido fuera de lo normal ("en mi casa"): handoff, sin cita.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "¿me pueden atender en mi casa?")
    ok = (r.get("handoff") and d.alertas_handoff
          and not d.citas and not d.botones)
    return ok, f"r={r} alertas={d.alertas_handoff} textos={d.textos}"


def h4():
    # Descuento por grupo: handoff, sin inventar el descuento.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "¿me hacen descuento si traigo a 5?")
    ok = (r.get("handoff") and not d.citas and "descuento" not in todo_texto(d))
    return ok, f"r={r} textos={d.textos}"


def h5():
    # Descuento inventado por la IA: R11 lo reemplaza de punta a punta.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "quiero descuento")
    ok = (d.textos == [FRASE_SEGURA] and "descuento" not in todo_texto(d)
          and not d.citas)
    return ok, f"r={r} textos={d.textos}"


def h6():
    # Re-pregunta tras un "ok": R13 la reemplaza de punta a punta.
    historial = [
        {"quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600 y no duele. ¿Cuál te interesa?"},
        {"quien_hablo": "cliente", "mensaje": "ok"},
    ]
    d = nuevo(clase=DepsPulida, historial=historial)
    r = msg(d, "ok")
    ok = (d.textos == ["¿Te ayudo con algo más?"])
    return ok, f"r={r} textos={d.textos}"


def h7():
    # Cancelación con error de dedo y cita real: se cancela de verdad.
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cliente = {"estatus": "agendado", "fecha_cita": H2,
               "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cliente)
    r = msg(d, "canselo mi cita")
    ok = bool(r.get("cita_cancelada")) and bool(d.citas_canceladas)
    return ok, f"r={r} canceladas={d.citas_canceladas} textos={d.textos}"


def h8():
    # Cambio con error de dedo y cita real: la vieja se cancela y se
    # pregunta el nuevo día (no se pierde el cambio).
    espejo = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                           notas="Paciente: Jose Ramon")]
    cliente = {"estatus": "agendado", "fecha_cita": H2,
               "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo(espejo=espejo, cliente=cliente)
    r = msg(d, "canbiar la cita")
    ok = bool(r.get("cita_cancelada")) and bool(d.citas_canceladas)
    return ok, f"r={r} canceladas={d.citas_canceladas} textos={d.textos}"


def h9():
    # Mensajes contradictorios seguidos: no se rompe y el embudo sigue.
    d = nuevo()
    r = msg(d, "quiero una cita el martes\nno, el martes no\nmejor el miércoles")
    ok = bool(r.get("respondio")) and bool(d.botones)
    return ok, f"r={r} textos={d.textos} botones={d.botones}"


def h10():
    # Dolor a las 3 am (cerrado): handoff + propuesta urgente con botones.
    d = nuevo(ahora=AHORA_CERRADO)
    r = msg(d, "me duele mucho la muela, es urgente", ahora=AHORA_CERRADO)
    ok = bool(r.get("handoff")) and bool(d.botones)
    return ok, f"r={r} botones={d.botones} textos={d.textos}"


def h11():
    # Cliente enojado: pasa a una persona con correo.
    d = nuevo(clase=DepsPulida)
    r = msg(d, "esto es una burla, ya me cansé")
    ok = (r.get("handoff") and d.alertas_handoff and not d.citas)
    return ok, f"r={r} alertas={d.alertas_handoff} textos={d.textos}"


def main():
    caso("A1 descuento inventado se desecha (R11)", a1)
    caso("A2 promoción inventada se desecha (R11)", a2)
    caso("A3 'no manejamos descuentos' pasa (R11)", a3)
    caso("A4 'sin descuentos' pasa (R11)", a4)
    caso("A5 Conocimiento con descuento permite mencionarlo (R11)", a5)
    caso("A6 'precio especial' inventado se desecha (R11)", a6)
    caso("A7 '100% segura' no es descuento (R11)", a7)
    caso("A8 sin texto de Conocimiento, R11 no aplica", a8)
    caso("B1 'tus pendientes' se limpia (R12)", b1)
    caso("B2 'pendiente' singular no se toca (R12)", b2)
    caso("B3 respuesta solo 'pendientes' → pregunta neutra (R12)", b3)
    caso("C1 re-pregunta tras 'ok' se reemplaza (R13)", c1)
    caso("C2 cliente repitió la pregunta: no se toca (R13)", c2)
    caso("C3 re-contestar con datos nuevos no es repetir (R13)", c3)
    caso("C4 repetición exacta sigue siendo R10", c4)
    caso("D1 'te propongo tu cita...' es oferta", d1)
    caso("D2 'te propongo que lo pienses' no es oferta", d2)
    caso("D3 'te propongo el martes...' es oferta", d3)
    caso("D4 estado detecta oferta verbal 'te propongo'", d4)
    caso("D5 R2 quita la oferta 'te propongo' en un saludo", d5)
    caso("E1 'canselo mi cita' cancela", e1)
    caso("E2 'cansela la cita' cancela", e2)
    caso("E3 'cancelo mi cita' cancela", e3)
    caso("E4 'anulo mi cita' cancela", e4)
    caso("E5 'canbiar la cita' cambia", e5)
    caso("E6 'cambair la cita' cambia", e6)
    caso("E7 negaciones con error de dedo no disparan", e7)
    caso("E8 regresiones de _intencion_cambio", e8)
    caso("F1 queja delicada 'no me gustó' se detecta", f1)
    caso("F2 quejas delicadas se detectan", f2)
    caso("F3 'me dolió después de la cita' es queja", f3)
    caso("F4 mensajes normales no son quejas", f4)
    caso("G1 guion de agent.py trae las entradas nuevas", g1)
    caso("G2 guion-robot.md sincronizado", g2)
    caso("H1 miedo: respuesta cálida, sin cita", h1)
    caso("H2 queja delicada: handoff con correo", h2)
    caso("H3 'en mi casa': handoff, sin cita", h3)
    caso("H4 descuento por grupo: handoff, sin inventar", h4)
    caso("H5 descuento inventado: R11 de punta a punta", h5)
    caso("H6 re-pregunta tras 'ok': R13 de punta a punta", h6)
    caso("H7 'canselo mi cita' cancela la cita real", h7)
    caso("H8 'canbiar la cita' mueve la cita real", h8)
    caso("H9 mensajes contradictorios: el embudo sigue", h9)
    caso("H10 dolor a las 3 am: handoff + propuesta urgente", h10)
    caso("H11 cliente enojado: handoff con correo", h11)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok "
          f"(pulida conversacional)")
    if fallos:
        print("Fallos:")
        for n in fallos:
            print(f"  - {n}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
