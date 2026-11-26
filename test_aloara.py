"""Pruebas Aloara (v3.21.0 + v3.22.0): identidad, correos y reporte mensual.

Cubre lo que Jose pidió el 2026-11-26:
- Aloara Weekly + reporte mensual (ventana, asunto, HTML, delta).
- Correos de alerta con voz Aloara y botón wa.me (Continuar
  conversación / Atender ahora / Ver oportunidad).
- Identidad del agente: asistente virtual transparente, firma
  Aloara opcional, protocolo de emergencia médica.
- Correo saliente configurable (v3.22.0): Gmail por defecto,
  iCloud con SMTP_* sin tocar código.

Uso:  python3 test_aloara.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
Sin internet: todo con fakes.
"""

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import robot.agent as agent_mod  # noqa: E402
import robot.mail as mail_mod  # noqa: E402
import robot.report as report_mod  # noqa: E402
from robot.config import correo_configurado, correo_saliente, settings  # noqa: E402

RESULTADOS = []


def caso(nombre, condicion, detalle=""):
    RESULTADOS.append((nombre, bool(condicion)))
    marca = "PASS" if condicion else "FAIL"
    print(f"[{marca}] {nombre}" + (f" :: {detalle}" if detalle and not condicion else ""))


class _MP:
    """Parche mínimo con restauración (sin pytest)."""

    def __init__(self):
        self._orig = []

    def set(self, obj, nombre, valor):
        self._orig.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)

    def restore(self):
        for obj, nombre, valor in reversed(self._orig):
            setattr(obj, nombre, valor)
        self._orig.clear()


class _DTFija(datetime):
    """datetime con now() fijo, para ventanas deterministas."""

    _ahora = datetime.fromisoformat("2026-12-15T10:00:00-07:00")

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls._ahora.astimezone(tz)
        return cls._ahora.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# A. Ventana del periodo (semanal / mensual)
# ---------------------------------------------------------------------------

def a1():
    mp = _MP()
    try:
        mp.set(report_mod, "datetime", _DTFija)
        desde, hasta, etiqueta, etiqueta_reporte = report_mod._ventana_periodo("mensual")
        ok = (
            desde.date().isoformat() == "2026-11-01"
            and hasta.date().isoformat() == "2026-12-01"
            and etiqueta_reporte == "MES 2026-11"
            and "2026" in etiqueta
        )
        return ok, f"desde={desde} hasta={hasta} et={etiqueta} er={etiqueta_reporte}"
    finally:
        mp.restore()


def a2():
    mp = _MP()
    try:
        mp.set(report_mod, "datetime", _DTFija)
        desde, hasta, etiqueta, etiqueta_reporte = report_mod._ventana_periodo("semanal")
        ok = (
            (hasta - desde) == timedelta(days=7)
            and etiqueta == etiqueta_reporte
            and "2026-12-08" in etiqueta
        )
        return ok, f"desde={desde} hasta={hasta} et={etiqueta}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# B. Reporte mensual de punta a punta (con fakes)
# ---------------------------------------------------------------------------

def _datos_mes():
    conversaciones = [
        {"fecha": "2026-11-20T10:00:00-07:00", "telefono": "111",
         "quien_hablo": "cliente", "mensaje": "hola", "robot_respondio": "si",
         "motivo": "Limpieza dental"},
    ]
    clientes = [
        {"fecha": "2026-11-20T10:00:00-07:00", "nombre": "Ana", "telefono": "111",
         "motivo": "Limpieza dental", "fecha_cita": "2026-11-25T10:00:00-07:00",
         "estatus": "agendado", "handoff": "no"},
    ]
    reporte = [
        {"semana": "MES 2026-10", "mensajes_atendidos": "3",
         "clientes_calificados": "1", "citas_agendadas": "1",
         "handoffs": "0", "resumen": "prev"},
    ]
    return conversaciones, clientes, reporte


def b1():
    mp = _MP()
    try:
        conversaciones, clientes, filas_reporte = _datos_mes()
        capturado = {}
        guardado = {}

        def leer_fake(pestana, spreadsheet_id=None):
            return {"Conversaciones": conversaciones, "Clientes": clientes,
                    "Citas": [], "Conocimiento": [],
                    "Reporte": filas_reporte}.get(pestana, [])

        def enviar_fake(dest, asunto, cuerpo, html=None):
            capturado.update(dest=dest, asunto=asunto, cuerpo=cuerpo, html=html)

        def guardar_fake(semana, *args):
            guardado["semana"] = semana

        mp.set(report_mod, "datetime", _DTFija)
        mp.set(report_mod, "leer_pestana", leer_fake)
        mp.set(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
        mp.set(report_mod, "enviar_correo", enviar_fake)
        mp.set(report_mod, "guardar_reporte", guardar_fake)
        mp.set(report_mod, "funcion_activa", lambda n: True)
        mp.set(report_mod, "nombre_negocio", lambda: "Clínica de prueba")
        mp.set(report_mod, "correo_dueno", lambda: "dueno@ejemplo.com")

        resultado = report_mod.generar_reporte_mensual()
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            capturado.get("asunto", "").startswith("Tu mes en Clínica de prueba")
            and "TU MES EN NÚMEROS" in html
            and "TU MES EN UNA LÍNEA" in html
            and "Aloara · Siempre presente" in html
            and "Manrope" in html
            and "Citas vs mes pasado: +0" in cuerpo
            and guardado.get("semana") == "MES 2026-11"
            and resultado.get("periodo") == "mensual"
            and resultado.get("delta_citas") == 0
        )
        return ok, f"asunto={capturado.get('asunto')!r} guardado={guardado} res={resultado}"
    finally:
        mp.restore()


def b2():
    # Regresión: el semanal sigue saliendo con su voz y su delta.
    mp = _MP()
    try:
        hoy = datetime.now(timezone.utc)
        iso = hoy.isoformat()
        conversaciones = [
            {"fecha": iso, "telefono": "111", "quien_hablo": "cliente",
             "mensaje": "hola", "robot_respondio": "si", "motivo": "Limpieza dental"},
        ]
        clientes = [
            {"fecha": iso, "nombre": "Ana", "telefono": "111",
             "motivo": "Limpieza dental", "fecha_cita": "2026-12-20T10:00:00-07:00",
             "estatus": "agendado", "handoff": "no"},
        ]
        capturado = {}

        def leer_fake(pestana, spreadsheet_id=None):
            return {"Conversaciones": conversaciones, "Clientes": clientes,
                    "Citas": [], "Conocimiento": [], "Reporte": []}.get(pestana, [])

        def enviar_fake(dest, asunto, cuerpo, html=None):
            capturado.update(dest=dest, asunto=asunto, cuerpo=cuerpo, html=html)

        mp.set(report_mod, "leer_pestana", leer_fake)
        mp.set(report_mod, "generar_texto", lambda *a, **k: "Resumen de prueba.")
        mp.set(report_mod, "enviar_correo", enviar_fake)
        mp.set(report_mod, "guardar_reporte", lambda *a, **k: None)
        mp.set(report_mod, "funcion_activa", lambda n: True)
        mp.set(report_mod, "nombre_negocio", lambda: "Clínica de prueba")
        mp.set(report_mod, "correo_dueno", lambda: "dueno@ejemplo.com")

        resultado = report_mod.generar_reporte_semanal()
        html = capturado.get("html", "") or ""
        ok = (
            capturado.get("asunto", "").startswith("Tu semana en Clínica de prueba")
            and "TU SEMANA EN NÚMEROS" in html
            and resultado.get("periodo") == "semanal"
        )
        return ok, f"asunto={capturado.get('asunto')!r} res={resultado}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# C. Correos de alerta con voz Aloara y botón wa.me
# ---------------------------------------------------------------------------

def _capturar_mail():
    mp = _MP()
    capturado = {}

    def enviar_fake(dest, asunto, cuerpo, html=None):
        capturado.update(dest=dest, asunto=asunto, cuerpo=cuerpo, html=html)

    mp.set(mail_mod, "enviar_correo", enviar_fake)
    mp.set(mail_mod, "correo_dueno", lambda: "dueno@ejemplo.com")
    return mp, capturado


def c1():
    mp, capturado = _capturar_mail()
    try:
        mail_mod.alerta_handoff(
            "Mariana R.", "5216694608263", "Solicita atención humana",
            "¿Me puede atender una persona?", "2026-11-26T12:42:00-07:00",
            resumen="Preguntó por limpieza y quiere hablar con alguien.",
            hilo="Cliente: hola\nRobot: claro, ¿en qué te ayudo?",
        )
        asunto = capturado.get("asunto", "")
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            asunto == "Una conversación necesita tu atención · Mariana R."
            and "Es momento de conectar." in cuerpo
            and "https://wa.me/5216694608263" in cuerpo
            and "Continuar conversación" in html
            and "https://wa.me/5216694608263" in html
            and "Aloara · Siempre presente" in html
            and "Manrope" in html
        )
        return ok, f"asunto={asunto!r} cuerpo={cuerpo[:200]!r}"
    finally:
        mp.restore()


def c2():
    mp, capturado = _capturar_mail()
    try:
        mail_mod.alerta_lead_caliente(
            "Carlos M.", "5216694608263", "Mazda CX-5",
            "Quiero una cotización", "2026-11-26T09:00:00-07:00",
        )
        asunto = capturado.get("asunto", "")
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            asunto.startswith("Una nueva oportunidad llegó a tu negocio")
            and "Tienes una nueva oportunidad." in cuerpo
            and "https://wa.me/5216694608263" in cuerpo
            and "Ver oportunidad" in html
        )
        return ok, f"asunto={asunto!r}"
    finally:
        mp.restore()


def c3():
    mp, capturado = _capturar_mail()
    try:
        mail_mod.alerta_cita_urgente(
            "Ana", "5216694608263", "Dolor de muela",
            "viernes 27 de noviembre, 11:30", "2026-11-26T12:48:00-07:00",
            razon="Dolor fuerte desde anoche",
        )
        asunto = capturado.get("asunto", "")
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            asunto.startswith("Atención prioritaria requerida")
            and "Tu equipo necesita intervenir." in cuerpo
            and "Dolor fuerte desde anoche" in cuerpo
            and "Atender ahora" in html
            and "https://wa.me/5216694608263" in html
        )
        return ok, f"asunto={asunto!r}"
    finally:
        mp.restore()


def c4():
    # Sin teléfono válido no hay botón, pero el correo sale igual.
    mp, capturado = _capturar_mail()
    try:
        mail_mod.alerta_handoff("Sin Tel", "", "motivo", "hola",
                                "2026-11-26T12:00:00-07:00")
        cuerpo = capturado.get("cuerpo", "")
        html = capturado.get("html", "") or ""
        ok = (
            "wa.me" not in cuerpo
            and "Continuar conversación" not in html
            and "Es momento de conectar." in cuerpo
        )
        return ok, f"cuerpo={cuerpo[:200]!r}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# D. Identidad del agente (guion)
# ---------------------------------------------------------------------------

def _guion_con(mp, firma=False, protocolo=""):
    mp.set(agent_mod, "nombre_recepcionista", lambda: "Ana")
    mp.set(agent_mod, "nombre_negocio", lambda: "")
    mp.set(agent_mod, "tipo_negocio", lambda: "una clínica")
    mp.set(agent_mod, "tono", lambda: "amigable")
    mp.set(agent_mod, "saludo_config", lambda: "")
    mp.set(agent_mod, "mensaje_fuera_horario", lambda: "")
    mp.set(agent_mod, "protocolo_urgencias", lambda: protocolo)
    mp.set(agent_mod, "funcion_activa", lambda n: True)
    mp.set(agent_mod, "interruptor",
           lambda clave, defecto="SI": firma if clave == "firma_aloara" else True)
    return agent_mod.guion()


def d1():
    mp = _MP()
    try:
        prompt = _guion_con(mp)
        ok = (
            "Eres Ana, el asistente virtual de una clínica" in prompt
            and "Nunca finjas ser una persona" in prompt
            and "asistente virtual de una clínica" in prompt
        )
        return ok, prompt[:300]
    finally:
        mp.restore()


def d2():
    mp = _MP()
    try:
        sin_firma = _guion_con(mp, firma=False)
        con_firma = _guion_con(mp, firma=True)
        ok = (
            "Firma Aloara autorizada" not in sin_firma
            and "Firma Aloara autorizada" in con_firma
            and "— Aloara" in con_firma
        )
        return ok, ""
    finally:
        mp.restore()


def d3():
    mp = _MP()
    try:
        sin_protocolo = _guion_con(mp, protocolo="")
        con_protocolo = _guion_con(mp, protocolo="Llama al 911 y avisa a recepción.")
        ok = (
            "Emergencia médica" in sin_protocolo
            and "911" in sin_protocolo
            and "Llama al 911 y avisa a recepción." in con_protocolo
            and "Una emergencia no se resuelve con una cita" not in con_protocolo
        )
        return ok, ""
    finally:
        mp.restore()


# ---------------------------------------------------------------------------
# E. Correo saliente configurable (Gmail o iCloud, v3.22.0)
# ---------------------------------------------------------------------------

def _limpiar_correo(mp):
    for attr in ("smtp_host", "smtp_port", "smtp_user", "smtp_password",
                 "gmail_user", "gmail_app_password"):
        mp.set(settings, attr, "")


def e1():
    mp = _MP()
    try:
        _limpiar_correo(mp)
        mp.set(settings, "smtp_host", "smtp.gmail.com")
        mp.set(settings, "smtp_port", 587)
        mp.set(settings, "gmail_user", "yo@gmail.com")
        mp.set(settings, "gmail_app_password", "xxxx")
        host, puerto, usuario, contrasena = correo_saliente()
        ok = (host == "smtp.gmail.com" and puerto == 587
              and usuario == "yo@gmail.com" and contrasena == "xxxx"
              and correo_configurado())
        return ok, f"saliente={(host, puerto, usuario)}"
    finally:
        mp.restore()


def e2():
    mp = _MP()
    try:
        _limpiar_correo(mp)
        mp.set(settings, "smtp_host", "smtp.mail.me.com")
        mp.set(settings, "smtp_port", 587)
        mp.set(settings, "smtp_user", "yo@icloud.com")
        mp.set(settings, "smtp_password", "yyyy")
        host, puerto, usuario, contrasena = correo_saliente()
        ok = (host == "smtp.mail.me.com" and puerto == 587
              and usuario == "yo@icloud.com" and contrasena == "yyyy"
              and correo_configurado())
        return ok, f"saliente={(host, puerto, usuario)}"
    finally:
        mp.restore()


def e3():
    mp = _MP()
    try:
        _limpiar_correo(mp)
        sin_nada = not correo_configurado()
        mp.set(settings, "smtp_user", "yo@icloud.com")
        mp.set(settings, "smtp_password", "yyyy")
        solo_smtp = correo_configurado()
        _limpiar_correo(mp)
        mp.set(settings, "gmail_user", "yo@gmail.com")
        mp.set(settings, "gmail_app_password", "xxxx")
        solo_gmail = correo_configurado()
        ok = sin_nada and solo_smtp and solo_gmail
        return ok, f"sin_nada={sin_nada} smtp={solo_smtp} gmail={solo_gmail}"
    finally:
        mp.restore()


class _FakeSMTP:
    capturado = []
    conexion = None
    login_args = None

    def __init__(self, host, puerto, timeout=30):
        _FakeSMTP.conexion = (host, puerto, timeout)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        _FakeSMTP.login_args = (u, p)

    def send_message(self, msg):
        _FakeSMTP.capturado.append(msg)


def e4():
    mp = _MP()
    try:
        _FakeSMTP.capturado = []
        _FakeSMTP.conexion = None
        _FakeSMTP.login_args = None
        _limpiar_correo(mp)
        mp.set(settings, "smtp_host", "smtp.mail.me.com")
        mp.set(settings, "smtp_port", 587)
        mp.set(settings, "smtp_user", "yo@icloud.com")
        mp.set(settings, "smtp_password", "yyyy")
        mp.set(smtplib, "SMTP", _FakeSMTP)
        mail_mod.enviar_correo("dueno@icloud.com", "Prueba", "Texto plano")
        msg = _FakeSMTP.capturado[0] if _FakeSMTP.capturado else None
        ok = (_FakeSMTP.conexion == ("smtp.mail.me.com", 587, 30)
              and _FakeSMTP.login_args == ("yo@icloud.com", "yyyy")
              and msg is not None and msg["From"] == "yo@icloud.com"
              and msg["To"] == "dueno@icloud.com")
        return ok, f"conexion={_FakeSMTP.conexion} login={_FakeSMTP.login_args}"
    finally:
        mp.restore()


def e5():
    mp = _MP()
    try:
        _limpiar_correo(mp)
        try:
            mail_mod.enviar_correo("dueno@ejemplo.com", "Prueba", "Texto")
            return False, "no levantó CorreoError"
        except mail_mod.CorreoError as exc:
            ok = "SMTP_USER" in str(exc) or "GMAIL_USER" in str(exc)
            return ok, f"exc={exc}"
    finally:
        mp.restore()


# ---------------------------------------------------------------------------

def main():
    caso("A1 Ventana mensual: mes calendario anterior", a1)
    caso("A2 Ventana semanal: últimos 7 días", a2)
    caso("B1 Reporte mensual de punta a punta", b1)
    caso("B2 Semanal sigue saliendo (regresión)", b2)
    caso("C1 Handoff Aloara Connect con botón wa.me", c1)
    caso("C2 Lead caliente Aloara Opportunities con botón", c2)
    caso("C3 Urgencia Aloara Priority con botón", c3)
    caso("C4 Sin teléfono: correo sale sin botón", c4)
    caso("D1 Guion: asistente virtual transparente", d1)
    caso("D2 Guion: firma Aloara solo si autorizada", d2)
    caso("D3 Guion: emergencia médica vs protocolo del negocio", d3)
    caso("E1 Correo saliente: por defecto Gmail", e1)
    caso("E2 Correo saliente: SMTP de iCloud manda", e2)
    caso("E3 Correo configurado: nada / solo SMTP / solo Gmail", e3)
    caso("E4 Enviar por iCloud: host, login y From correctos", e4)
    caso("E5 Sin correo configurado: error claro", e5)

    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} ok")
    if fallos:
        print("Fallaron:", ", ".join(fallos))
        sys.exit(1)


if __name__ == "__main__":
    main()
