"""Auditoría de negocio — sistema de reportes (v3.20.5).

Métricas de retorno para el cliente que paga, calculadas con datos
que ya existen en las hojas (nada inventado):
- Valor estimado en pesos de las citas agendadas, desde los precios
  de Conocimiento (solo si el servicio cruza con UN precio claro).
- Conversaciones atendidas fuera de horario (con el horario de
  Conocimiento; sin horario configurado no se afirma nada).
- Clientes que volvieron y agendaron (recuperados).
- Delta de citas vs la semana anterior (desde la pestaña Reporte).

Uso:  python3 test_auditoria_reportes.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import robot.report as report_mod  # noqa: E402
from robot.report import (  # noqa: E402
    clientes_que_volvieron,
    conversaciones_fuera_de_horario,
    delta_citas_semana_anterior,
    valor_estimado_citas,
)

RESULTADOS = []


def caso(nombre, fn):
    try:
        ok, detalle = fn()
    except Exception as exc:
        ok, detalle = False, f"excepción {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok))
    marca = "PASS" if ok else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not ok else ""))


CONOCIMIENTO = [
    {"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental",
     "respuesta_o_precio": "$600", "detalle": "Dura 60 minutos"},
    {"tipo": "servicio", "pregunta_o_servicio": "Revisión y diagnóstico",
     "respuesta_o_precio": "$200", "detalle": "Dura 30 minutos"},
    {"tipo": "servicio", "pregunta_o_servicio": "Blanqueamiento dental",
     "respuesta_o_precio": "$1,800", "detalle": "Dura 60 minutos"},
    {"tipo": "servicio", "pregunta_o_servicio": "Paquete doble",
     "respuesta_o_precio": "$600 o $1,800 según el caso", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Lunes a viernes",
     "respuesta_o_precio": "09:00 a 18:00", "detalle": ""},
    {"tipo": "horario", "pregunta_o_servicio": "Sábado",
     "respuesta_o_precio": "09:00 a 14:00", "detalle": ""},
]

# Ventana fija: domingo 22 a martes 24 de nov 2026 (hora Mazatlán, UTC-7).
DESDE = datetime.fromisoformat("2026-11-22T00:00:00-07:00")
HASTA = datetime.fromisoformat("2026-11-24T00:00:00-07:00")


def _cli(fecha, telefono, motivo="Limpieza dental", estatus="agendado"):
    return {"fecha": fecha, "nombre": "Ana", "telefono": telefono,
            "motivo": motivo, "fecha_cita": "2026-11-25T10:00:00-07:00",
            "estatus": estatus, "handoff": "no"}


def _conv(fecha, telefono="6671", quien="cliente", respondio="si"):
    return {"fecha": fecha, "telefono": telefono, "quien_hablo": quien,
            "mensaje": "hola", "robot_respondio": respondio, "motivo": "Limpieza dental"}


# ---------------------------------------------------------------------------
# A. Valor estimado en pesos
# ---------------------------------------------------------------------------

def a1():
    citas = [_cli("2026-11-23T10:00:00-07:00", "1", "Limpieza dental"),
             _cli("2026-11-23T11:00:00-07:00", "2", "Blanqueamiento dental")]
    total, con, sin = valor_estimado_citas(citas, CONOCIMIENTO)
    ok = (total, con, sin) == (2400, 2, 0)
    return ok, f"total={total} con={con} sin={sin}"


def a2():
    # Servicio sin precio conocido: no se suma, no se inventa.
    citas = [_cli("2026-11-23T10:00:00-07:00", "1", "Extracción de muela")]
    total, con, sin = valor_estimado_citas(citas, CONOCIMIENTO)
    ok = (total, con, sin) == (0, 0, 1)
    return ok, f"total={total} con={con} sin={sin}"


def a3():
    # Fila ambigua (dos montos distintos): no se adivina.
    citas = [_cli("2026-11-23T10:00:00-07:00", "1", "Paquete doble")]
    total, con, sin = valor_estimado_citas(citas, CONOCIMIENTO)
    ok = (total, con, sin) == (0, 0, 1)
    return ok, f"total={total} con={con} sin={sin}"


def a4():
    # Sin Conocimiento: todo sin precio, total 0.
    citas = [_cli("2026-11-23T10:00:00-07:00", "1")]
    total, con, sin = valor_estimado_citas(citas, [])
    ok = (total, con, sin) == (0, 0, 1)
    return ok, f"total={total} con={con} sin={sin}"


def a5():
    # Coincidencia parcial: "limpieza" cruza con "Limpieza dental".
    citas = [_cli("2026-11-23T10:00:00-07:00", "1", "limpieza")]
    total, con, sin = valor_estimado_citas(citas, CONOCIMIENTO)
    ok = (total, con, sin) == (600, 1, 0)
    return ok, f"total={total} con={con} sin={sin}"


# ---------------------------------------------------------------------------
# B. Fuera de horario
# ---------------------------------------------------------------------------

def b1():
    # Lunes 2:00 am (cerrado) cuenta; lunes 10:00 am no.
    convs = [
        _conv("2026-11-23T02:00:00-07:00", "1"),
        _conv("2026-11-23T10:00:00-07:00", "2"),
    ]
    n = conversaciones_fuera_de_horario(convs, CONOCIMIENTO, DESDE, HASTA)
    ok = n == 1
    return ok, f"n={n}"


def b2():
    # Domingo (el negocio no abre) cuenta como fuera de horario.
    convs = [_conv("2026-11-22T11:00:00-07:00", "1")]
    n = conversaciones_fuera_de_horario(convs, CONOCIMIENTO, DESDE, HASTA)
    ok = n == 1
    return ok, f"n={n}"


def b3():
    # Sábado 10:00 (abierto 09:00-14:00) no cuenta; sábado 20:00 sí.
    convs = [
        _conv("2026-11-21T10:00:00-07:00", "1"),
        _conv("2026-11-21T20:00:00-07:00", "2"),
    ]
    desde = datetime.fromisoformat("2026-11-21T00:00:00-07:00")
    n = conversaciones_fuera_de_horario(convs, CONOCIMIENTO, desde, HASTA)
    ok = n == 1
    return ok, f"n={n}"


def b4():
    # Sin horario en Conocimiento: None (sin dato, no se afirma nada).
    convs = [_conv("2026-11-23T02:00:00-07:00", "1")]
    n = conversaciones_fuera_de_horario(convs, [], DESDE, HASTA)
    ok = n is None
    return ok, f"n={n}"


def b5():
    # Solo cuentan las que el robot SÍ atendió (cliente + respondió).
    convs = [
        _conv("2026-11-23T02:00:00-07:00", "1", quien="robot"),
        _conv("2026-11-23T02:00:00-07:00", "2", respondio="no"),
    ]
    n = conversaciones_fuera_de_horario(convs, CONOCIMIENTO, DESDE, HASTA)
    ok = n == 0
    return ok, f"n={n}"


# ---------------------------------------------------------------------------
# C. Clientes que volvieron y agendaron
# ---------------------------------------------------------------------------

def c1():
    clientes = [
        _cli("2026-11-23T10:00:00-07:00", "111"),   # volvió (escribió antes)
        _cli("2026-11-23T11:00:00-07:00", "222"),   # nuevo esta semana
        _cli("2026-11-23T12:00:00-07:00", "333", estatus="en conversacion"),
    ]
    convs = [
        _conv("2026-11-10T10:00:00-07:00", "111"),
        _conv("2026-11-23T09:00:00-07:00", "222"),
        _conv("2026-11-10T10:00:00-07:00", "333"),
    ]
    n = clientes_que_volvieron(clientes, convs, DESDE, HASTA)
    ok = n == 1
    return ok, f"n={n}"


def c2():
    # Sin conversaciones previas: nadie volvió.
    clientes = [_cli("2026-11-23T10:00:00-07:00", "111")]
    n = clientes_que_volvieron(clientes, [], DESDE, HASTA)
    ok = n == 0
    return ok, f"n={n}"


# ---------------------------------------------------------------------------
# D. Delta vs semana anterior
# ---------------------------------------------------------------------------

def d1():
    desde = datetime.fromisoformat("2026-11-23T00:00:00-07:00")
    hasta = datetime.fromisoformat("2026-11-30T00:00:00-07:00")
    filas = [{"semana": "2026-11-16 a 2026-11-23", "citas_agendadas": "3"}]
    delta = delta_citas_semana_anterior(filas, desde, hasta, 5)
    ok = delta == 2
    return ok, f"delta={delta}"


def d2():
    desde = datetime.fromisoformat("2026-11-23T00:00:00-07:00")
    hasta = datetime.fromisoformat("2026-11-30T00:00:00-07:00")
    delta = delta_citas_semana_anterior([], desde, hasta, 5)
    ok = delta is None
    return ok, f"delta={delta}"


def d3():
    # Fila de otra semana: no se usa.
    desde = datetime.fromisoformat("2026-11-23T00:00:00-07:00")
    hasta = datetime.fromisoformat("2026-11-30T00:00:00-07:00")
    filas = [{"semana": "2026-11-09 a 2026-11-16", "citas_agendadas": "3"}]
    delta = delta_citas_semana_anterior(filas, desde, hasta, 5)
    ok = delta is None
    return ok, f"delta={delta}"


# ---------------------------------------------------------------------------
# E. Integración: el reporte semanal trae las líneas de retorno
# ---------------------------------------------------------------------------

class _MP:
    """Monkeypatch mínimo sin pytest."""

    def __init__(self):
        self._orig = []

    def setattr(self, obj, nombre, valor):
        self._orig.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)

    def restore(self):
        for obj, nombre, valor in reversed(self._orig):
            setattr(obj, nombre, valor)
        self._orig = []


def e1():
    mp = _MP()
    try:
        hoy = datetime.now(timezone.utc)
        desde = hoy - timedelta(days=7)
        iso = hoy.isoformat()
        hace_20d = (hoy - timedelta(days=20)).isoformat()
        conversaciones = [
            _conv(iso, "111"),
            _conv(iso, "222"),
            _conv(hace_20d, "111"),  # el 111 ya había escrito antes
        ]
        clientes = [
            _cli(iso, "111", "Limpieza dental"),
            _cli(iso, "222", "Blanqueamiento dental"),
        ]
        espejo = []
        semana_prev = f"{(desde - timedelta(days=7)).date()} a {desde.date()}"
        filas_reporte = [
            {"semana": semana_prev, "mensajes_atendidos": "5",
             "clientes_calificados": "1", "citas_agendadas": "1",
             "handoffs": "0", "resumen": "prev"},
        ]

        def leer_fake(pestana, spreadsheet_id=None):
            return {"Conversaciones": conversaciones, "Clientes": clientes,
                    "Citas": espejo, "Conocimiento": CONOCIMIENTO,
                    "Reporte": filas_reporte}.get(pestana, [])

        capturado = {}

        def enviar_fake(dest, asunto, cuerpo, html=None):
            capturado["cuerpo"] = cuerpo
            capturado["html"] = html

        mp.setattr(report_mod, "leer_pestana", leer_fake)
        mp.setattr(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
        mp.setattr(report_mod, "enviar_correo", enviar_fake)
        mp.setattr(report_mod, "guardar_reporte", lambda *a, **k: None)
        mp.setattr(report_mod, "funcion_activa", lambda n: True)
        mp.setattr(report_mod, "nombre_negocio", lambda: "Clínica de prueba")
        mp.setattr(report_mod, "correo_dueno", lambda: "dueno@ejemplo.com")

        resultado = report_mod.generar_reporte_semanal()
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            "Valor estimado de las citas agendadas: $2,400 MXN" in cuerpo
            and "Clientes que volvieron y agendaron: 1" in cuerpo
            and "Citas vs semana pasada: +1" in cuerpo
            and "$2,400" in html and "MXN" in html
            and resultado.get("valor_estimado") == 2400
            and resultado.get("delta_citas") == 1
        )
        return ok, f"cuerpo={cuerpo[:400]!r} resultado={resultado}"
    finally:
        mp.restore()


def e2():
    # Sin precios conocidos ni horario: las líneas de pesos y de
    # fuera de horario NO salen (no se afirma nada sin dato), pero
    # el correo sale igual.
    mp = _MP()
    try:
        hoy = datetime.now(timezone.utc)
        iso = hoy.isoformat()
        conversaciones = [_conv(iso, "111")]
        clientes = [_cli(iso, "111", "Servicio sin precio")]

        def leer_fake(pestana, spreadsheet_id=None):
            return {"Conversaciones": conversaciones, "Clientes": clientes,
                    "Citas": [], "Conocimiento": [], "Reporte": []}.get(pestana, [])

        capturado = {}

        def enviar_fake(dest, asunto, cuerpo, html=None):
            capturado["cuerpo"] = cuerpo
            capturado["html"] = html

        mp.setattr(report_mod, "leer_pestana", leer_fake)
        mp.setattr(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
        mp.setattr(report_mod, "enviar_correo", enviar_fake)
        mp.setattr(report_mod, "guardar_reporte", lambda *a, **k: None)
        mp.setattr(report_mod, "funcion_activa", lambda n: True)
        mp.setattr(report_mod, "nombre_negocio", lambda: "Clínica de prueba")
        mp.setattr(report_mod, "correo_dueno", lambda: "dueno@ejemplo.com")

        resultado = report_mod.generar_reporte_semanal()
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            "Valor estimado de las citas agendadas" not in cuerpo
            and "fuera de tu horario" not in cuerpo
            and "CITAS CONFIRMADAS" in cuerpo
            and "$" not in html
            and "llegaron fuera de tu horario" not in html
            and resultado.get("valor_estimado") == 0
            and resultado.get("fuera_de_horario") is None
        )
        return ok, f"cuerpo={cuerpo[:400]!r}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# F. Render v3 (v3.20.8): el diseño aprobado por Jose
# ---------------------------------------------------------------------------

def e3():
    # Render directo con datos completos: el número es el titular,
    # están las secciones v3, la línea de pérdida y el pie.
    html = report_mod._html_reporte_semanal(
        nombre_neg="Clínica de prueba", semana="2026-11-17 a 2026-11-24",
        citas=[{"nombre": "Ana", "motivo": "Limpieza dental",
                "fecha_cita": "2026-11-25T10:00:00-07:00"}],
        humanos=[{"nombre": "Roberto", "motivo": "dolor de muela",
                  "fecha": "2026-11-23T08:15:00-07:00"}],
        recuperar=[{"nombre": "Sofía", "motivo": "blanqueamiento"}],
        atendidos=46, resueltas=41, pct=89, citas_n=1,
        canceladas=0, no_show=0, horas=3.4, sin_respuesta=0,
        resumen="Resumen de prueba.",
        confirmaciones=4, valor=3800, citas_con_precio=1,
        fuera_horario=6, volvieron=2, delta=2,
    )
    ok = (
        "$3,800" in html and "MXN" in html
        and "Clínica de prueba" in html
        and "2026-11-17 a 2026-11-24" in html
        and "CITAS CONFIRMADAS" in html and "Ana" in html
        and "NECESITA TU ATENCIÓN" in html and "Roberto" in html
        and "¿Te aparto un lugar esta semana?" in html
        and "TU SEMANA EN UNA LÍNEA" in html
        and "Resumen de prueba." in html
        and "6 llegaron fuera de tu horario" in html
        and "Aloara · Siempre presente" in html
        and "Valores estimados con base en tus precios." in html
        and "Manrope" in html
    )
    return ok, html[:300]


def e4():
    # Sin precio conocido ni fuera de horario: el HTML no inventa
    # pesos (ningún "$") ni afirma la línea de pérdida.
    html = report_mod._html_reporte_semanal(
        nombre_neg="Clínica de prueba", semana="2026-11-17 a 2026-11-24",
        citas=[{"nombre": "Ana", "motivo": "Servicio sin precio",
                "fecha_cita": "2026-11-25T10:00:00-07:00"}],
        humanos=[], recuperar=[],
        atendidos=3, resueltas=3, pct=100, citas_n=1,
        canceladas=0, no_show=0, horas=0.2, sin_respuesta=0,
        resumen="Resumen de prueba.",
        valor=0, citas_con_precio=0, fuera_horario=None,
    )
    ok = (
        "$" not in html
        and "llegaron fuera de tu horario" not in html
        and "1 cita confirmada" in html
        and "Nada pendiente esta semana." in html
    )
    return ok, html[:300]


def e5():
    # El texto del negocio se escapa: nada de HTML inyectado.
    html = report_mod._html_reporte_semanal(
        nombre_neg="<script>alert(1)</script>",
        semana="2026-11-17 a 2026-11-24",
        citas=[], humanos=[], recuperar=[],
        atendidos=0, resueltas=0, pct=0, citas_n=0,
        canceladas=0, no_show=0, horas=0.0, sin_respuesta=0,
        resumen="<b>resumen</b>",
    )
    ok = (
        "&lt;script&gt;" in html and "<script>alert" not in html
        and "&lt;b&gt;resumen" in html and "<b>resumen</b>" not in html
    )
    return ok, html[:300]


def main():
    for nombre, fn in [
        ("A1 valor estimado suma citas con precio", a1),
        ("A2 servicio sin precio no suma", a2),
        ("A3 fila ambigua no suma", a3),
        ("A4 sin Conocimiento todo sin precio", a4),
        ("A5 coincidencia parcial de servicio", a5),
        ("B1 fuera de horario: madrugada sí, mañana no", b1),
        ("B2 domingo (cerrado) cuenta", b2),
        ("B3 sábado: abierto no, noche sí", b3),
        ("B4 sin horario configurado: None", b4),
        ("B5 solo cuentan las atendidas por el robot", b5),
        ("C1 cliente que volvió y agendó cuenta", c1),
        ("C2 sin previas nadie volvió", c2),
        ("D1 delta vs semana anterior", d1),
        ("D2 sin fila previa: None", d2),
        ("D3 fila de otra semana no se usa", d3),
        ("E1 reporte semanal con líneas de retorno", e1),
        ("E2 sin datos de retorno el correo sale sin afirmar", e2),
        ("E3 render v3: número, secciones y línea de pérdida", e3),
        ("E4 sin precio: sin $ inventado ni línea de pérdida", e4),
        ("E5 el HTML escapa el texto del negocio", e5),
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
