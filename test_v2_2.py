"""Pruebas de la versión 2.2, SIN internet.

Cubre solo lo nuevo de la v2.2 (lo anterior sigue en test_simulado.py
y test_v2.py):
(a) fuera de horario: se guarda la propuesta y el cliente queda
    registrado como lead (antes se perdía todo).
(b) un "sí" por texto confirma la cita, aunque siga siendo de noche
    (antes, el "sí" nocturno volvía a ofrecer lo mismo en bucle).
(c) un "sí, mejor el sábado" NO confirma: pide otro día, va al agente.
(d) una propuesta vieja (más de 48 h) no se confirma con un "sí".
(e) fusionar_cliente: un cliente, una fila. El estatus nunca baja
    (agendado no vuelve a "en conversacion") y el handoff "si" se queda.
(f) contar_semana cuenta clientes distintos, no filas.

Uso:  python test_v2_2.py
"""

from datetime import datetime, timedelta, timezone

import robot.logic as logic_mod
from robot.agent import RespuestaAgente
from robot.logic import atender_boton, atender_mensaje, contar_semana
from robot.sheets import fusionar_cliente

CONOCIMIENTO_CON_HORARIO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Servicio 1",
     "respuesta_o_precio": "$500", "detalle": "Dura 60 minutos"},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]

FOTOS = [{"descripcion": "Foto del local", "url": "https://ejemplo.com/foto-local.jpg"}]


class DepsV22:
    """Servicios de mentira: guardan todo en memoria (como en test_v2)."""

    def __init__(self, conocimiento=None, agente=None):
        self.agente = agente or RespuestaAgente(
            respuesta_texto="Claro. Te ayudo con eso. ¿Qué día te viene mejor?")
        self.conocimiento = conocimiento if conocimiento is not None else CONOCIMIENTO_CON_HORARIO
        self.conversaciones = []
        self.clientes = []
        self.textos_enviados = []
        self.citas = []
        self.alertas = []
        self.llamadas_agente = []

    def leer_control(self):
        return {"bot_activo": "SI", "ultima_respuesta_humana": ""}

    def leer_conocimiento(self):
        return self.conocimiento

    def leer_fotos(self):
        return FOTOS

    def leer_historial(self, telefono):
        return [c for c in self.conversaciones if c["telefono"] == telefono]

    def registrar_conversacion(self, fecha, telefono, quien, mensaje, respondio, motivo=""):
        self.conversaciones.append({"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
                                    "mensaje": mensaje, "robot_respondio": respondio, "motivo": motivo})

    def registrar_cliente(self, fecha, nombre, telefono, motivo, fecha_cita="", origen="whatsapp",
                          estatus="en conversacion", handoff="no"):
        self.clientes.append({"fecha": fecha, "nombre": nombre, "telefono": telefono,
                              "motivo": motivo, "fecha_cita": fecha_cita, "origen": origen,
                              "estatus": estatus, "handoff": handoff})

    def preguntar_agente(self, mensaje, conocimiento, fotos, historial):
        self.llamadas_agente.append(mensaje)
        return self.agente

    def enviar_texto(self, telefono, texto):
        self.textos_enviados.append((telefono, texto))

    def enviar_foto(self, telefono, url):
        pass

    def crear_cita(self, nombre, telefono, motivo, fecha_cita):
        inicio = datetime.fromisoformat(fecha_cita)
        fin = inicio + timedelta(minutes=60)
        cita = {"inicio": inicio.isoformat(), "fin": fin.isoformat()}
        self.citas.append(cita)
        return cita

    def alerta_handoff(self, nombre, telefono, motivo, ultimo_mensaje, fecha):
        self.alertas.append((nombre, telefono, motivo))

    def marcar_leido_y_escribiendo(self, message_id):
        pass

    def enviar_botones(self, telefono, texto, botones):
        pass

    def alerta_error(self, motivo, telefono, ultimo_mensaje, fecha):
        pass


RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def limpiar_propuestas():
    logic_mod._CITAS_PENDIENTES.clear()


def main():
    # Domingo 2026-11-15 a las 20:00 (hora de Mazatlán) = 03:00 UTC del lunes.
    domingo_noche = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)
    domingo_noche_5 = datetime(2026, 11, 16, 3, 5, tzinfo=timezone.utc)

    # (a) Fuera de horario: propuesta guardada + lead registrado.
    limpiar_propuestas()
    d = DepsV22()
    r = atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                         con_ritmo=False, ahora=domingo_noche)
    caso("(a) Fuera de horario: se guarda la propuesta para el lunes 09:00",
         r.get("cita_propuesta") is True and r.get("fecha_cita", "").startswith("2026-11-16T09:00"),
         f"r={r}")
    caso("(a) Fuera de horario: el cliente queda registrado como lead",
         len(d.clientes) == 1 and d.clientes[0]["telefono"] == "6671234567"
         and d.clientes[0]["fecha_cita"].startswith("2026-11-16T09:00"),
         f"clientes={d.clientes}")
    caso("(a) Fuera de horario: no llama al agente ni crea la cita todavía",
         len(d.citas) == 0 and not d.llamadas_agente)

    # (b) Un "sí" por texto, de noche, confirma la cita.
    r2 = atender_mensaje(d, "6671234567", "Ana", "Sí, me va",
                          con_ritmo=False, ahora=domingo_noche_5)
    caso("(b) 'Sí, me va' de noche: la cita se crea",
         len(d.citas) == 1 and d.citas[0]["inicio"].startswith("2026-11-16T09:00"),
         f"citas={d.citas}")
    caso("(b) 'Sí, me va' de noche: confirmación bonita con día y hora",
         any("16 de noviembre" in t and "09:00" in t for _, t in d.textos_enviados),
         f"textos={d.textos_enviados}")
    caso("(b) 'Sí' por texto: no vuelve a llamar al agente",
         len(d.llamadas_agente) == 0, f"llamadas={d.llamadas_agente}")

    # (c) "Sí, mejor el sábado" NO confirma.
    limpiar_propuestas()
    d = DepsV22()
    atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                     con_ritmo=False, ahora=domingo_noche)
    r = atender_mensaje(d, "6671234567", "Ana", "Sí, mejor el sábado",
                         con_ritmo=False, ahora=domingo_noche_5)
    caso("(c) 'Sí, mejor el sábado': NO crea la cita",
         len(d.citas) == 0, f"citas={d.citas}")

    # (d) Propuesta vieja (más de 48 h) no se confirma.
    limpiar_propuestas()
    d = DepsV22()
    atender_mensaje(d, "6671234567", "Ana", "Quiero una cita",
                     con_ritmo=False, ahora=domingo_noche)
    tres_dias_despues = domingo_noche + timedelta(days=3)
    r = atender_mensaje(d, "6671234567", "Ana", "Sí",
                         con_ritmo=False, ahora=tres_dias_despues)
    caso("(d) Propuesta de hace 3 días: un 'sí' no la confirma",
         len(d.citas) == 0, f"citas={d.citas}")

    # (b2) Un "sí" por texto también confirma una propuesta normal (de día).
    limpiar_propuestas()
    agente_agenda = RespuestaAgente(
        respuesta_texto="Perfecto, Ana.",
        nombre="Ana", motivo="Quiere agendar una cita",
        fecha_cita="2026-11-14T10:00:00", quiere_agendar="si")
    d = DepsV22(agente=agente_agenda)
    lunes_manana = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)
    atender_mensaje(d, "6671234567", "Ana", "Soy Ana, quiero cita el sábado a las 10",
                     con_ritmo=False, ahora=lunes_manana)
    r = atender_mensaje(d, "6671234567", "Ana", "Sí",
                         con_ritmo=False, ahora=lunes_manana)
    caso("(b2) 'Sí' por texto tras proponer cita: se crea, sin botón",
         len(d.citas) == 1, f"citas={d.citas}")
    # El botón sigue funcionando igual que antes.
    limpiar_propuestas()
    d = DepsV22(agente=agente_agenda)
    atender_mensaje(d, "6671234567", "Ana", "Soy Ana, quiero cita",
                     con_ritmo=False, ahora=lunes_manana)
    r = atender_boton(d, "6671234567", "Ana", "confirmar_cita", con_ritmo=False)
    caso("(b2) Botón Confirmar: sigue creando la cita",
         len(d.citas) == 1 and r.get("cita") is not None, f"r={r}")

    # (e) fusionar_cliente: un cliente, una fila.
    viejo = {"fecha": "2026-11-12T10:00:00", "nombre": "Ana", "telefono": "6671234567",
             "motivo": "Quiere cita", "fecha_cita": "2026-11-14T10:00:00",
             "origen": "whatsapp", "estatus": "agendado", "handoff": "no"}
    nuevo = {"fecha": "2026-11-13T10:00:00", "nombre": "", "telefono": "6671234567",
             "motivo": "Preguntó por precios", "fecha_cita": "",
             "origen": "whatsapp", "estatus": "en conversacion", "handoff": "si"}
    fusion = fusionar_cliente(viejo, nuevo)
    caso("(e) Fusionar: fecha nueva, nombre y cita viejos se conservan",
         fusion[0] == "2026-11-13T10:00:00" and fusion[1] == "Ana"
         and fusion[4] == "2026-11-14T10:00:00", f"fusion={fusion}")
    caso("(e) Fusionar: el estatus NUNCA baja de agendado",
         fusion[6] == "agendado", f"fusion={fusion}")
    caso("(e) Fusionar: el handoff 'si' se queda",
         fusion[7] == "si", f"fusion={fusion}")
    caso("(e) Fusionar: el motivo nuevo sí reemplaza al viejo",
         fusion[3] == "Preguntó por precios", f"fusion={fusion}")

    # (f) contar_semana: 3 filas del mismo teléfono = 1 cliente.
    conv = [{"fecha": "2026-11-12T10:00:00+00:00", "quien_hablo": "robot",
             "robot_respondio": "si", "motivo": ""}]
    cli = [{"fecha": "2026-11-12T10:00:00+00:00", "telefono": "6671234567",
            "estatus": "en conversacion", "handoff": "no"},
           {"fecha": "2026-11-12T11:00:00+00:00", "telefono": "6671234567",
            "estatus": "en conversacion", "handoff": "no"},
           {"fecha": "2026-11-12T12:00:00+00:00", "telefono": "6671234567",
            "estatus": "calificado", "handoff": "no"}]
    desde = datetime(2026, 11, 10, tzinfo=timezone.utc)
    hasta = datetime(2026, 11, 17, tzinfo=timezone.utc)
    conteo = contar_semana(conv, cli, desde, hasta)
    caso("(f) contar_semana: 3 filas del mismo teléfono = 1 cliente",
         conteo["clientes_calificados"] == 1, f"conteo={conteo}")

    pasaron = sum(1 for _, ok in RESULTADOS if ok)
    print(f"\n{pasaron}/{len(RESULTADOS)} casos pasaron.")
    raise SystemExit(0 if pasaron == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
