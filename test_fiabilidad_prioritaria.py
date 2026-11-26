"""Regresiones de recuperación, pausa por conversación y firma del webhook.

Ejecutar: python test_fiabilidad_prioritaria.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

import app
from robot.agrupar import Agrupador
from robot import booking, logic, mail, report, sheets


class FiabilidadPrioritaria(unittest.TestCase):
    def test_recuperacion_local_espera_y_es_secuencial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "buzon.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"vistos": ["a", "b"], "pendientes": {
                    "1": {"entradas": [[1, 1, "primero", "a"]], "nombre": ""},
                    "2": {"entradas": [[2, 2, "segundo", "b"]], "nombre": ""},
                }}, f)
            llamadas = []
            activo = 0
            maximo = 0
            def callback(tel, nombre, textos, ids):
                nonlocal activo, maximo
                activo += 1
                maximo = max(maximo, activo)
                llamadas.append((tel, textos))
                activo -= 1
            ag = Agrupador(callback, espera_segundos=0.01, archivo=path)
            self.assertEqual(ag.cargar(programar=False), 2)
            self.assertEqual(llamadas, [])
            ag.procesar_recuperados()
            self.assertEqual(llamadas, [("1", ["primero"]), ("2", ["segundo"])])
            self.assertEqual(maximo, 1)
            self.assertFalse(ag.agregar("1", "repetido", wamid="a"))

    def test_pausa_por_telefono_y_vencimiento(self):
        class Deps:
            def __init__(self):
                self.pausas = {}
            def pausar_conversacion(self, tel, hasta):
                self.pausas[tel] = hasta
            def leer_pausa_hasta(self, tel):
                return self.pausas.get(tel, "")
        deps = Deps()
        now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        with patch.object(logic.settings, "pausa_humano_horas", 2):
            logic._pausar_conversacion(deps, "1", now)
        self.assertTrue(logic._pausa_conversacion_activa(deps, "1", now + timedelta(minutes=119)))
        self.assertFalse(logic._pausa_conversacion_activa(deps, "2", now))
        self.assertFalse(logic._pausa_conversacion_activa(deps, "1", now + timedelta(hours=2)))

    def test_handoff_pausa_solo_esa_conversacion_y_los_botones(self):
        from test_pulida_agrupamiento import DepsAgrupamiento

        class DepsConPausa(DepsAgrupamiento):
            def __init__(self, ahora):
                super().__init__(ahora=ahora)
                self.pausas = {}
            def pausar_conversacion(self, tel, hasta):
                self.pausas[tel] = hasta
            def leer_pausa_hasta(self, tel):
                return self.pausas.get(tel, "")

        now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
        deps = DepsConPausa(now)
        with patch.object(logic.settings, "pausa_humano_horas", 2):
            primero = logic.atender_boton(deps, "521111", "Ana", "hablar_persona", con_ritmo=False, ahora=now)
            bloqueado = logic.atender_boton(deps, "521111", "Ana", "confirmar_cita", con_ritmo=False, ahora=now + timedelta(minutes=1))
            otro = logic.atender_boton(deps, "522222", "Beto", "hablar_persona", con_ritmo=False, ahora=now + timedelta(minutes=1))
        self.assertTrue(primero["handoff"])
        self.assertFalse(bloqueado["respondio"])
        self.assertTrue(otro["handoff"])

    def test_pausa_guardada_se_lee_por_telefono(self):
        filas = [
            {"telefono": "1", "quien_hablo": "sistema", "motivo": "pausa_hasta", "fecha": "2026-11-26T12:00:00+00:00"},
            {"telefono": "2", "quien_hablo": "sistema", "motivo": "pausa_hasta", "fecha": "2026-11-26T14:00:00+00:00"},
            {"telefono": "1", "quien_hablo": "cliente", "motivo": "", "fecha": "2026-11-26T11:00:00+00:00"},
        ]
        with patch.object(sheets, "leer_pestana", return_value=filas):
            self.assertEqual(sheets.leer_pausa_hasta("1"), "2026-11-26T12:00:00+00:00")
            self.assertEqual(sheets.leer_pausa_hasta("3"), "")

    def test_alertas_no_incluyen_texto_libre_sensible(self):
        alertas = [
            lambda: mail.alerta_error("dolor secreto", "521111", "dolor secreto", "ahora"),
            lambda: mail.alerta_cita_confirmada("Ana", "521111", "dolor secreto", "ahora", "ahora"),
            lambda: mail.alerta_cita_urgente("Ana", "521111", "dolor secreto", "ahora", "ahora", razon="dolor secreto"),
            lambda: mail.alerta_lead_caliente("Ana", "521111", "dolor secreto", "dolor secreto", "ahora"),
            lambda: mail.alerta_cita_pendiente("Ana", "521111", "dolor secreto", "ahora", "ahora"),
            lambda: mail.alerta_handoff("Ana", "521111", "dolor secreto", "dolor secreto", "ahora", resumen="dolor secreto", hilo="dolor secreto"),
        ]
        enviados = []
        with patch.object(mail, "correo_dueno", return_value="dueno@example.test"), patch.object(mail, "enviar_correo", side_effect=lambda d, a, c, html=None: enviados.append((a, c, html))):
            for alerta in alertas:
                alerta()
        self.assertEqual(len(enviados), len(alertas))
        for asunto, cuerpo, html in enviados:
            self.assertNotIn("dolor secreto", asunto + cuerpo + html)
            self.assertIn("https://wa.me/521111", cuerpo)

    def test_html_reporte_no_filtra_motivos_de_salud(self):
        sensible = "dolor secreto de salud"
        html = report._html_reporte_semanal(
            nombre_neg="Clínica", semana="semana", citas=[{"nombre": "Ana", "motivo": sensible, "fecha_cita": "2026-12-01T09:00:00-07:00"}],
            humanos=[{"nombre": "Beto", "motivo": sensible, "fecha": "2026-11-26T12:00:00+00:00"}],
            recuperar=[{"nombre": "Caro", "motivo": sensible}], atendidos=3, resueltas=2, pct=67,
            citas_n=1, canceladas=0, no_show=0, horas=0.1, sin_respuesta=0, resumen="Sin detalles privados.")
        self.assertNotIn(sensible, html)
        self.assertIn("Ana", html)
        self.assertIn("Beto", html)

    def test_cancelacion_solo_fecha_y_telefono_exactos(self):
        class Servicio:
            def __init__(self):
                self.borrados = []
            def events(self):
                return self
            def delete(self, **kwargs):
                self.borrados.append(kwargs["eventId"])
                return self
            def execute(self):
                return {}
        servicio = Servicio()
        eventos = [
            {"id": "primera", "summary": "Cita Ana — 521111", "start": {"dateTime": "2026-12-01T09:00:00-07:00"}},
            {"id": "segunda", "summary": "Cita Ana — 521111", "start": {"dateTime": "2026-12-01T10:00:00-07:00"}},
            {"id": "ajena", "summary": "Cita Beto — 999521111", "start": {"dateTime": "2026-12-01T09:00:00-07:00"}},
        ]
        with patch.object(booking, "_servicio_calendar", return_value=servicio), patch.object(booking, "_eventos_del_dia", return_value=eventos):
            self.assertTrue(booking.cancelar_cita("521111", "2026-12-01T09:00:00-07:00"))
            self.assertEqual(servicio.borrados, ["primera"])
            self.assertFalse(booking.cancelar_cita("521111", "2026-12-01T11:00:00-07:00"))

    def test_si_calendar_no_confirma_no_se_afirma_cancelacion(self):
        from test_bateria_dinamica import DepsDinamica
        now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
        cliente = {"nombre": "Ana", "telefono": "521111", "estatus": "agendado", "fecha_cita": "2026-11-24T09:00:00-07:00"}
        deps = DepsDinamica(cliente=cliente, ahora=now)
        deps.cancelar_cita = lambda tel, fecha: False
        resultado = logic._atender_cambio_cancelacion(deps, "521111", "Ana", now.isoformat(), "cancelar", con_ritmo=False, ahora=now)
        self.assertFalse(resultado["cita_cancelada"])
        self.assertTrue(resultado["handoff"])
        self.assertTrue(any("No pude confirmar" in texto for texto in deps.textos))
        self.assertFalse(any("quedó cancelada" in texto for texto in deps.textos))

    def test_freebusy_con_error_no_se_considera_libre(self):
        with patch.object(booking.settings, "calendar_id", "primary"):
            with self.assertRaises(RuntimeError):
                booking._ocupaciones({"calendars": {"primary": {"errors": [{"reason": "notFound"}]}}})
            with self.assertRaises(RuntimeError):
                booking._ocupaciones({"calendars": {}})
            self.assertEqual(booking._ocupaciones({"calendars": {"primary": {"busy": []}}}), [])

    def test_contexto_fecha_aislada_y_cliente_recurrente(self):
        from test_pulida_agrupamiento import DepsAgrupamiento
        now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
        d = DepsAgrupamiento(ahora=now)
        with patch.object(logic, "funcion_activa", return_value=True), patch.object(logic, "canal_negocio_activo", return_value=True):
            logic.atender_mensaje(d, "521111", "", "para pasado mañana a las 7 de la tarde", con_ritmo=False, ahora=now)
        contexto = d.mensajes_agente[-1]
        self.assertIn("Pasado mañana es miércoles 25 de noviembre", contexto)
        self.assertIn("huecos libres", contexto.lower())
        cliente = {"nombre": "Ana Pérez", "estatus": "agendado", "fecha_cita": "2026-11-16T09:00:00-07:00", "motivo": "Limpieza"}
        d = DepsAgrupamiento(cliente=cliente, ahora=now)
        with patch.object(logic, "funcion_activa", return_value=True), patch.object(logic, "canal_negocio_activo", return_value=True):
            logic.atender_mensaje(d, "522222", "", "hola buenas tardes", con_ritmo=False, ahora=now)
        contexto = d.mensajes_agente[-1]
        self.assertIn("Ana Pérez", contexto)
        self.assertIn("No vuelvas a pedir su nombre", contexto)
        self.assertIn("Su última cita fue", contexto)

    def test_propuesta_no_inventa_disponibilidad_si_calendar_falla(self):
        from test_bateria_dinamica import CONOCIMIENTO
        ahora = datetime(2026, 11, 13, 16, tzinfo=timezone.utc)
        propuesta = "2026-11-15T19:00:00-07:00"
        lunes = "2026-11-16T09:00:00-07:00"
        class Agenda:
            def hora_libre(self, fecha):
                return fecha == lunes
        self.assertEqual(logic._corregir_fecha_propuesta(propuesta, CONOCIMIENTO, ahora, Agenda(), ["2026-11-14T10:00:00-07:00", lunes]), lunes)
        class Fallo:
            def hora_libre(self, fecha):
                raise RuntimeError("Calendar caído")
        self.assertIsNone(logic._corregir_fecha_propuesta(propuesta, CONOCIMIENTO, ahora, Fallo(), [lunes]))
        self.assertIsNone(logic._corregir_fecha_propuesta(propuesta, CONOCIMIENTO, ahora, object(), [lunes]))
        with patch.object(booking, "hora_libre", side_effect=RuntimeError("Calendar caído")):
            with self.assertRaises(RuntimeError):
                app.DependenciasReales().hora_libre(lunes)

    def test_respaldo_conserva_solo_precio_documentado_y_no_propone(self):
        from test_simulacion_profunda import nuevo, msg, propuesta_actual, todo_texto, limpiar
        limpiar()
        d = nuevo()
        resultado = msg(d, "hola buenas tardes quiero saber cuánto cuesta la limpieza y si "
                          "tienen horario el sábado y dónde están ubicados y si me pueden "
                          "agendar para el martes por favor")
        self.assertIn("$600", todo_texto(d))
        self.assertIn("Sábado: 09:00 a 14:00", todo_texto(d))
        self.assertIn("Av. del Mar 123, Mazatlán", todo_texto(d))
        self.assertIn("No puedo confirmar la disponibilidad", todo_texto(d))
        self.assertIsNone(propuesta_actual())
        self.assertFalse(resultado.get("cita_propuesta", False))
        conocimiento = [{"tipo": "servicio", "pregunta_o_servicio": "Limpieza dental", "respuesta_o_precio": "$600"},
                        {"tipo": "servicio", "pregunta_o_servicio": "Limpieza profunda", "respuesta_o_precio": "$900"}]
        self.assertEqual(logic._precio_documentado_para_respaldo("cuánto cuesta la limpieza", conocimiento), "")
        self.assertEqual(logic._precio_documentado_para_respaldo("cuánto cuesta", conocimiento), "")
        limpiar()

    def test_dolor_y_medicacion_fuerzan_respaldo_y_handoff(self):
        from test_bateria_dinamica import DepsDinamica, AHORA_ABIERTO, TEL
        from robot.agent import RespuestaAgente
        class ConPausa(DepsDinamica):
            def __init__(self):
                super().__init__(ahora=AHORA_ABIERTO)
                self.pausas = {}
            def pausar_conversacion(self, tel, hasta):
                self.pausas[tel] = hasta
            def leer_pausa_hasta(self, tel):
                return self.pausas.get(tel, "")
        logic._CITAS_PENDIENTES.clear()
        d = ConPausa()
        d.preguntar_agente = lambda *args: RespuestaAgente(
            respuesta_texto="Toma ibuprofeno y espera.", confianza="alta")
        with patch.object(logic, "funcion_activa", return_value=True), patch.object(logic, "canal_negocio_activo", return_value=True):
            resultado = logic.atender_mensaje(d, TEL, "", "Me duele mucho una muela, ¿qué tomo?", con_ritmo=False, ahora=AHORA_ABIERTO)
        self.assertTrue(resultado.get("handoff"))
        self.assertTrue(d.alertas_handoff)
        self.assertTrue(any("No puedo recomendarte medicamentos" in t and "atención médica inmediata" in t for t in d.textos))
        self.assertFalse(any("ibuprofeno" in t.lower() for t in d.textos))
        self.assertIn(TEL, d.pausas)
        self.assertFalse(d.botones, "No ofrecer botones bloqueados por la pausa")
        self.assertNotIn(TEL, logic._CITAS_PENDIENTES)
        logic._CITAS_PENDIENTES.clear()

    def test_mover_y_adelantar_no_confirman_cancelacion_incierta(self):
        from test_bateria_dinamica import DepsDinamica, AHORA_ABIERTO, TEL, H2
        class Agenda(DepsDinamica):
            def __init__(self):
                super().__init__(ahora=AHORA_ABIERTO)
                self.pausas = {}
            def pausar_conversacion(self, tel, hasta):
                self.pausas[tel] = hasta
            def cancelar_cita(self, telefono, fecha):
                return False
        for tipo, confirmar in (("mover", logic._confirmar_mover),
                                ("adelanto", logic._confirmar_adelanto)):
            for fallo in ("cancelar", "freebusy"):
                with self.subTest(tipo=tipo, fallo=fallo):
                    logic._CITAS_PENDIENTES.clear()
                    d = Agenda()
                    if fallo == "freebusy":
                        d.hora_libre = lambda fecha: (_ for _ in ()).throw(RuntimeError("Calendar"))
                    logic._CITAS_PENDIENTES[TEL] = {
                        "tipo": tipo, "fecha_cita": H2, "fecha_bonita": "martes 24 a las 09:00",
                        "fecha_vieja": "2026-11-25T09:00:00-07:00", "motivo": "limpieza",
                    }
                    r = confirmar(d, TEL, "Ana", AHORA_ABIERTO.isoformat(), con_ritmo=False, ahora=AHORA_ABIERTO)
                    self.assertTrue(r["handoff"])
                    self.assertIn(TEL, d.pausas)
                    self.assertTrue(d.alertas_handoff)
                    self.assertFalse(d.actualizaciones)
                    self.assertTrue(any("No pude verificar el cambio" in t for t in d.textos))
                    self.assertEqual(len(d.citas), int(fallo == "cancelar"))
                    self.assertNotIn(TEL, logic._CITAS_PENDIENTES)
        logic._CITAS_PENDIENTES.clear()

    def test_lote_durable_agrupa_textos_y_resuelve_interactivo(self):
        filas = [
            (2, "a", {"mensaje": {"from": "521111", "type": "text", "text": {"body": "hola"}}, "contacts": []}),
            (3, "b", {"mensaje": {"from": "521111", "type": "text", "text": {"body": "quiero cita"}}, "contacts": []}),
            (4, "c", {"mensaje": {"from": "521111", "type": "text", "text": {"body": "para mañana"}}, "contacts": []}),
        ]
        with patch.object(app, "atender_mensaje") as atender:
            app._procesar_lote_durable(filas)
        self.assertEqual(atender.call_args.args[3], "hola\nquiero cita\npara mañana")
        self.assertEqual(atender.call_args.kwargs["message_id"], "a")
        boton = [(5, "d", {"mensaje": {"from": "521111", "type": "interactive", "interactive": {"button_reply": {"id": "hablar_persona"}}}, "contacts": []})]
        with patch.object(app, "atender_boton") as atender:
            app._procesar_lote_durable(boton)
        self.assertEqual(atender.call_args.args[3], "hablar_persona")

    def test_webhook_guarda_antes_de_confirmar_y_reintenta_si_falla(self):
        cuerpo = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.1", "from": "521111", "type": "text", "text": {"body": "hola"}}]}}]}]}).encode()
        signature = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
        async def enviar():
            scope = {"type": "http", "method": "POST", "path": "/webhook", "headers": [(b"x-hub-signature-256", signature.encode())]}
            async def receive():
                return {"type": "http.request", "body": cuerpo, "more_body": False}
            return await app.recibir_whatsapp(Request(scope, receive))
        orden = []
        class Cola:
            def guardar(self, mensajes):
                orden.append(("guardado", mensajes[0][0]["id"]))
                return 1
        class Trabajador:
            def avisar(self):
                orden.append(("avisado",))
        with patch.object(app.settings, "meta_app_secret", "secreto"), patch.object(app, "_COLA", Cola()), patch.object(app, "_TRABAJADOR", Trabajador()):
            self.assertEqual(asyncio.run(enviar()), {"ok": True})
        self.assertEqual(orden, [("guardado", "wamid.1"), ("avisado",)])
        with patch.object(app.settings, "meta_app_secret", "secreto"), patch.object(app._COLA, "guardar", side_effect=OSError("sin red")):
            self.assertEqual(asyncio.run(enviar()).status_code, 503)

    def test_webhook_exige_secreto_y_firma(self):
        cuerpo = b'{"entry": []}'
        async def enviar(secret, signature):
            headers = [(b"x-hub-signature-256", signature.encode())] if signature else []
            scope = {"type": "http", "method": "POST", "path": "/webhook", "headers": headers}
            async def receive():
                return {"type": "http.request", "body": cuerpo, "more_body": False}
            with patch.object(app.settings, "meta_app_secret", secret):
                return await app.recibir_whatsapp(Request(scope, receive))
        signature = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
        self.assertEqual(asyncio.run(enviar("", "")).status_code, 503)
        self.assertEqual(asyncio.run(enviar("secreto", "sha256=incorrecta")).status_code, 403)
        self.assertEqual(asyncio.run(enviar("secreto", signature)), {"ok": True})


if __name__ == "__main__":
    unittest.main()
