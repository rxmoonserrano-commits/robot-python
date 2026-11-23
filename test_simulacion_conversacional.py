"""Simulación conversacional (v3.19): viajes multi-turno completos.

Jose pidió una corrida puramente conversacional para adelantarse
a los bugs y asegurar calidad. Las corridas anteriores probaban
mensajes sueltos; esta prueba CONVERSACIONES COMPLETAS (5 a 9
turnos cada una), que es donde viven los bugs de contexto: memoria
que se pierde entre turnos, propuestas que se pisan, embudos que
se rompen a mitad, regresos tras días sin contexto, urgencias en
medio de una charla...

Cada viaje es un cliente de verdad con un objetivo, y se verifica
al final: citas creadas (cuántas y cuándo), correos, handoffs,
propuesta viva o consumida, y que la IA recibió el contexto
(qué días pasaron, qué cita tiene, qué preguntó antes).

Uso:  python3 test_simulacion_conversacional.py
Salida: 0 = todo ok; 1 = algún viaje falló (se imprime por qué).
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_bateria_dinamica import (  # noqa: E402
    AHORA_ABIERTO,
    H1,
    H2,
    H3,
    HUECOS,
    NOMBRE,
    TEL,
    _fila_espejo,
    _propuesta_base,
)
from test_simulacion_profunda import (  # noqa: E402
    DepsProfunda,
    btn,
    limpiar,
    msg,
    nuevo,
    propuesta_actual,
    todo_texto,
)

RESULTADOS = []


def escenario(nombre, fn):
    limpiar()
    try:
        ok, detalle = fn()
    except Exception as exc:
        ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok))
    marca = "PASS" if ok else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not ok else ""))
    limpiar()


class DepsConversacional(DepsProfunda):
    """Registra además el contexto completo que recibe la IA."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mensajes_agente = []

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.mensajes_agente.append(mensaje)
        return super().preguntar_agente(mensaje, conocimiento, fotos, historial)


def nuevo_c(**kw):
    d = DepsConversacional(**{k: v for k, v in kw.items()
                              if k in ("espejo", "historial", "cliente", "ahora")})
    if kw.get("propuesta") is not None:
        from robot.logic import _CITAS_PENDIENTES
        _CITAS_PENDIENTES[TEL] = dict(kw["propuesta"])
    return d


def contexto_recibido(d, fragmento):
    """¿La IA recibió ese fragmento de contexto en algún turno?"""
    return any(fragmento.lower() in m.lower() for m in d.mensajes_agente)


# ============================================================
# Viajes
# ============================================================

def j1():
    # Cliente nuevo completo: saluda, pregunta, agenda, confirma.
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "¿a qué hora abren el sábado?")
    msg(d, "quiero agendar mañana")
    if propuesta_actual() is None:
        return False, "no se creó la propuesta tras agendar"
    msg(d, "sí")
    ok = (len(d.citas) == 1 and d.citas[0]["fecha_cita"] in HUECOS
          and propuesta_actual() is None and bool(d.textos))
    return ok, f"citas={d.citas} propuesta={propuesta_actual() is not None}"


def j2():
    # Cliente que duda y regresa tras días: memoria y tiempo.
    hist = [
        {"fecha": "2026-11-17T10:00:00+00:00", "quien_hablo": "cliente",
         "mensaje": "¿cuánto cuesta la limpieza?"},
        {"fecha": "2026-11-17T10:01:00+00:00", "quien_hablo": "robot",
         "mensaje": "La limpieza cuesta $600."},
    ]
    cli = {"estatus": "en conversacion", "motivo": "limpieza", "nombre": NOMBRE,
           "resumen_conversacion": "Preguntó precios de limpieza."}
    d = nuevo_c(historial=hist, cliente=cli)
    msg(d, "hola de nuevo")
    if not contexto_recibido(d, "Hace"):
        return False, "la IA no recibió el contexto de días desde el último mensaje"
    if not contexto_recibido(d, "Preguntó precios de limpieza"):
        return False, "la IA no recibió la memoria del cliente (resumen)"
    msg(d, "quiero agendar mañana")
    msg(d, "sí")
    ok = len(d.citas) == 1
    return ok, f"citas={len(d.citas)} texto={todo_texto(d)[:120]!r}"


def j3():
    # Dos citas en una conversación: la suya y la de su hermana.
    from robot.agent import RespuestaAgente
    d = nuevo_c()
    d.agente_override = RespuestaAgente(
        respuesta_texto="Te propongo tu cita.",
        quiere_agendar="si", accion="agendar",
        fecha_cita=H2, motivo="Blanqueamiento dental")
    msg(d, "quiero agendar para mí el martes")
    p = propuesta_actual() or {}
    if p.get("cita2") is not None:
        pass
    msg(d, "sí")
    if len(d.citas) != 1:
        return False, f"primera confirmación creó {len(d.citas)} citas"
    d.agente_override = RespuestaAgente(
        respuesta_texto="Te propongo la cita de tu hermana.",
        quiere_agendar="si", accion="agendar",
        fecha_cita=H3, motivo="Revisión y diagnóstico",
        nombre_paciente="Ana Torres", relacion_paciente="su hermana")
    msg(d, "ahora quiero agendar para mi hermana el miércoles")
    msg(d, "sí")
    ok = len(d.citas) == 2
    return ok, f"citas={len(d.citas)}"


def j4():
    # Cambia de idea a mitad: agenda, se arrepiente, reagenda otro día.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    if propuesta_actual() is None:
        return False, "no se creó la primera propuesta"
    msg(d, "no, mejor no")
    if d.citas:
        return False, "confirmó pese al 'no'"
    msg(d, "quiero agendar el miércoles")
    msg(d, "sí")
    ok = len(d.citas) == 1 and d.citas[0]["fecha_cita"] == H3
    return ok, f"citas={d.citas}"


def j5():
    # Cancela y vuelve: cita → cancelar → reagendar → confirmar.
    esp = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                        notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "quiero cancelar")
    if len(d.citas_canceladas) != 1:
        return False, f"canceladas={d.citas_canceladas}"
    msg(d, "mejor quiero agendar el miércoles")
    msg(d, "sí")
    ok = len(d.citas) == 1 and d.citas[0]["fecha_cita"] == H3
    return ok, f"citas={d.citas} canceladas={len(d.citas_canceladas)}"


def j6():
    # Urgencia en medio de una conversación tranquila.
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "me duele mucho la muela, es urgente")
    if not d.alertas_handoff:
        return False, "la urgencia en medio no pasó a una persona"
    if propuesta_actual() is None:
        return False, "la urgencia no dejó propuesta de cita"
    msg(d, "sí")
    ok = len(d.citas) == 1 and len(d.alertas_urgentes) == 1
    return ok, f"citas={len(d.citas)} urgentes={len(d.alertas_urgentes)}"


def j7():
    # Enojado en medio del embudo: handoff, sin confirmar.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    if propuesta_actual() is None:
        return False, "no se creó la propuesta"
    msg(d, "estoy muy enojado con el servicio")
    ok = bool(d.alertas_handoff) and not d.citas
    return ok, f"handoff={d.alertas_handoff} citas={d.citas}"


def j8():
    # Cliente que pregunta mucho antes de agendar (5 preguntas).
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "¿a qué hora abren el sábado?")
    msg(d, "¿dónde están ubicados?")
    msg(d, "¿tienen fotos del local?")
    msg(d, "¿qué incluye la limpieza?")
    if d.citas:
        return False, "creó cita sin que el cliente agendara"
    msg(d, "quiero agendar mañana")
    msg(d, "sí")
    ok = len(d.citas) == 1 and "$600" in todo_texto(d)
    return ok, f"citas={len(d.citas)} texto={todo_texto(d)[:120]!r}"


def j9():
    # Pide persona en medio del embudo: handoff, sin cita.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    msg(d, "quiero hablar con una persona")
    ok = bool(d.alertas_handoff) and not d.citas
    return ok, f"handoff={d.alertas_handoff} citas={d.citas}"


def j10():
    # Tope y mover conversacional: 2 citas → agendar → mover → sí.
    esp = [
        _fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                     notas="Paciente: Jose Ramon"),
        _fila_espejo("C-2", "2026-11-25", "09:00", "10:00",
                     notas="Paciente: su hermana"),
    ]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "quiero agendar mañana")
    p = propuesta_actual() or {}
    if p.get("tipo") != "mover":
        return False, f"tope no ofreció mover (tipo={p.get('tipo')})"
    msg(d, "sí")
    ok = len(d.citas_canceladas) == 1 and len(d.citas) == 1
    return ok, f"canceladas={len(d.citas_canceladas)} citas={len(d.citas)}"


def j11():
    # Confirma asistencia y luego pregunta otra cosa: no crea nada.
    esp = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                        notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "ahí nos vemos")
    if not any("confirm" in (u["notas"] or "").lower() for u in d.actualizaciones):
        return False, "no registró la confirmación de asistencia"
    msg(d, "¿cuánto cuesta la limpieza?")
    ok = not d.citas and "$600" in todo_texto(d)
    return ok, f"citas={d.citas} texto={todo_texto(d)[:120]!r}"


def j12():
    # Spam y basura en medio: la conversación se recupera.
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "compra mi curso de trading")
    msg(d, "asdfgh")
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "quiero agendar mañana")
    msg(d, "sí")
    ok = len(d.citas) == 1 and "$600" in todo_texto(d)
    return ok, f"citas={len(d.citas)} texto={todo_texto(d)[:120]!r}"


def j13():
    # "Lo voy a pensar" con propuesta viva, y luego confirma.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    msg(d, "lo voy a pensar")
    if d.citas:
        return False, "confirmó con 'lo voy a pensar'"
    if propuesta_actual() is None:
        return False, "perdió la propuesta tras 'lo voy a pensar'"
    msg(d, "sí")
    ok = len(d.citas) == 1
    return ok, f"citas={len(d.citas)}"


def j14():
    # Adelanto por urgencia conversacional: cita martes → urgencia
    # lunes → adelantar → cita movida, sin duplicar.
    esp = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                        notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "me duele mucho la muela, es urgente")
    p = propuesta_actual() or {}
    if p.get("tipo") != "adelanto":
        return False, f"urgencia no ofreció adelanto (tipo={p.get('tipo')})"
    if not d.alertas_handoff:
        return False, "urgencia sin handoff"
    btn(d, "adelantar_cita")
    ok = (len(d.citas) == 1 and len(d.citas_canceladas) == 1
          and len(d.alertas_urgentes) == 1)
    return ok, (f"citas={len(d.citas)} canceladas={len(d.citas_canceladas)} "
                f"urgentes={len(d.alertas_urgentes)}")


def j15():
    # Pregunta con propuesta pendiente: responde y la propuesta sigue.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    if propuesta_actual() is None:
        return False, "no se creó la propuesta"
    msg(d, "¿cuánto cuesta la limpieza?")
    if "$600" not in todo_texto(d):
        return False, "no respondió el precio con propuesta pendiente"
    if propuesta_actual() is None:
        return False, "perdió la propuesta al preguntar"
    msg(d, "sí")
    ok = len(d.citas) == 1
    return ok, f"citas={len(d.citas)}"


def j16():
    # Cita inminente: la IA recibe cuánto falta para la cita.
    esp = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                        notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "hola")
    ok = contexto_recibido(d, "Su cita es")
    return ok, f"contexto cita recibido={ok} texto={todo_texto(d)[:120]!r}"


def j17():
    # Cliente que se despide y vuelve al día siguiente.
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "gracias, ya no")
    if not any(m["proxima_accion"] == "cerrada" for m in d.memorias):
        return False, "no marcó la conversación como cerrada"
    msg(d, "hola de nuevo, ¿cuánto cuesta la limpieza?")
    ok = "$600" in todo_texto(d) and not d.citas
    return ok, f"texto={todo_texto(d)[:120]!r}"


def j18():
    # Cambiar con dos citas: el cliente cambia LA SUYA (la de Clientes)
    # y la otra se re-propone junto con la nueva (retomar). El retomar
    # viaja por el botón Cambiar hora de una propuesta de dos citas:
    # se cambia una y la otra se guarda para re-proponerla.
    from test_simulacion_profunda import btn
    p = _propuesta_base(AHORA_ABIERTO)
    p["cita2"] = {"fecha_cita": H3, "fecha_bonita": "miércoles 25 de noviembre a las 09:00",
                  "motivo": "Revisión y diagnóstico",
                  "nombre_paciente": "Ana Torres",
                  "relacion_paciente": "su hermana",
                  "numero_paciente": "5216691112222", "profesional": ""}
    d = nuevo_c(propuesta=p)
    r = btn(d, "cambiar_hora")
    if not d.botones:
        return False, f"cambiar hora con dos citas no ofreció elegir cuál: {r}"
    btn(d, "cambiar_mia")
    msg(d, "quiero agendar el miércoles")
    p2 = propuesta_actual() or {}
    if p2.get("cita2") is None:
        return False, "la otra cita no se re-propuso con la nueva (retomar)"
    msg(d, "sí")
    ok = len(d.citas) == 2
    return ok, f"citas={len(d.citas)}"


def j19():
    # Dos urgencias seguidas: la segunda no duplica la propuesta.
    d = nuevo_c()
    msg(d, "me duele mucho la muela, es urgente")
    if propuesta_actual() is None:
        return False, "primera urgencia sin propuesta"
    msg(d, "sigo con mucho dolor, es urgente")
    if len(d.alertas_handoff) != 2:
        return False, f"segunda urgencia sin handoff (handoff={len(d.alertas_handoff)})"
    if propuesta_actual() is None:
        return False, "perdió la propuesta tras la segunda urgencia"
    msg(d, "sí")
    ok = len(d.citas) == 1
    return ok, f"citas={len(d.citas)} handoff={len(d.alertas_handoff)}"


def j20():
    # Cita para otra persona: la cita sale a nombre de ella.
    from robot.agent import RespuestaAgente
    d = nuevo_c()
    d.agente_override = RespuestaAgente(
        respuesta_texto="Te propongo tu cita.",
        quiere_agendar="si", accion="agendar",
        fecha_cita=H2, motivo="Blanqueamiento dental",
        nombre_paciente="Ana Torres", relacion_paciente="su hermana",
        numero_paciente="5216691112222")
    msg(d, "quiero agendar para mi hermana Ana el martes")
    msg(d, "sí")
    ok = len(d.citas) == 1 and d.citas[0]["nombre"] == "Ana Torres"
    return ok, f"citas={d.citas}"


def j21():
    # Confirma, cancela, y luego "confirma asistencia" sin cita:
    # nada se crea de la nada. (La cancelación por texto necesita la
    # cita en Clientes; aquí se siembra la fila como en producción.)
    esp = [_fila_espejo("C-1", "2026-11-24", "09:00", "10:00",
                        notas="Paciente: Jose Ramon")]
    cli = {"estatus": "agendado", "fecha_cita": H2,
           "motivo": "Blanqueamiento dental", "nombre": NOMBRE}
    d = nuevo_c(espejo=esp, cliente=cli)
    msg(d, "quiero cancelar")
    if len(d.citas_canceladas) != 1:
        return False, f"no canceló: {d.citas_canceladas}"
    msg(d, "confirmo mi asistencia")
    ok = not d.citas and len(d.citas_canceladas) == 1
    return ok, f"citas={d.citas} canceladas={len(d.citas_canceladas)}"


def j22():
    # Memoria al final del viaje: el robot aprendió algo del cliente.
    # (La memoria se guarda cuando la IA manda resumen/interés; el
    # agente falso manda resumen en el cierre "gracias, ya no".)
    d = nuevo_c()
    msg(d, "hola")
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "gracias, ya no")
    ok = len(d.memorias) >= 1 and any(
        m["proxima_accion"] == "cerrada" for m in d.memorias)
    return ok, f"memorias={d.memorias}"


def j23():
    # "No" pelón con propuesta = esa hora no; luego reagenda y confirma.
    d = nuevo_c()
    msg(d, "quiero agendar mañana")
    msg(d, "no")
    if d.citas:
        return False, "confirmó con un 'no' pelón"
    msg(d, "quiero agendar el miércoles")
    msg(d, "sí")
    ok = len(d.citas) == 1 and d.citas[0]["fecha_cita"] == H3
    return ok, f"citas={d.citas}"


def j24():
    # Pregunta → agendar → pregunta con propuesta → confirma.
    # La propuesta sobrevive a dos preguntas seguidas.
    d = nuevo_c()
    msg(d, "¿cuánto cuesta la limpieza?")
    msg(d, "quiero agendar mañana")
    msg(d, "¿a qué hora abren el sábado?")
    msg(d, "¿dónde están ubicados?")
    if propuesta_actual() is None:
        return False, "perdió la propuesta tras dos preguntas"
    msg(d, "sí")
    ok = len(d.citas) == 1
    return ok, f"citas={len(d.citas)}"


def main():
    viajes = [
        ("J1 cliente nuevo completo: saluda→precio→horario→agenda→confirma", j1),
        ("J2 duda y regresa tras días: memoria + tiempo llegan a la IA", j2),
        ("J3 dos citas en una charla: la suya y la de su hermana", j3),
        ("J4 cambia de idea a mitad: agenda→no→reagenda→confirma", j4),
        ("J5 cancela y vuelve: cancelar→reagendar→confirmar", j5),
        ("J6 urgencia en medio de la charla: handoff+propuesta→cita urgente", j6),
        ("J7 enojado en el embudo: handoff sin confirmar", j7),
        ("J8 pregunta 5 cosas antes de agendar: embudo intacto", j8),
        ("J9 pide persona en el embudo: handoff sin cita", j9),
        ("J10 tope y mover conversacional: mover→sí→movida, sin duplicar", j10),
        ("J11 confirma asistencia y pregunta otra cosa: sin crear", j11),
        ("J12 spam y basura en medio: la charla se recupera", j12),
        ("J13 'lo voy a pensar' con propuesta viva: luego confirma", j13),
        ("J14 adelanto por urgencia: cita martes→urgencia→adelantar→movida", j14),
        ("J15 pregunta con propuesta pendiente: responde y sigue", j15),
        ("J16 cita inminente: la IA recibe cuánto falta", j16),
        ("J17 se despide y vuelve: cerrada→regreso con precio", j17),
        ("J18 cambiar con dos citas: cambia la suya, la otra se re-propone", j18),
        ("J19 dos urgencias seguidas: handoff ×2, una sola propuesta", j19),
        ("J20 cita para otra persona: sale a nombre de ella", j20),
        ("J21 confirma→cancela→'confirma asistencia': nada se crea de la nada", j21),
        ("J22 memoria al final del viaje: el robot aprendió algo", j22),
        ("J23 'no' pelón = esa hora no: reagenda y confirma", j23),
        ("J24 dos preguntas con propuesta viva: sobrevive y confirma", j24),
    ]
    for nombre, fn in viajes:
        escenario(nombre, fn)

    fallos = [n for n, ok in RESULTADOS if not ok]
    print()
    if fallos:
        print(f"FALLOS ({len(fallos)}):")
        for n in fallos:
            print(f"  - {n}")
        sys.exit(1)
    print(f"{len(RESULTADOS)}/{len(RESULTADOS)} viajes ok "
          f"(simulación conversacional)")


if __name__ == "__main__":
    main()
