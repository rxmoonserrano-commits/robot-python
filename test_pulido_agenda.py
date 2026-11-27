"""Regresiones de seguridad y rendimiento de Calendar, sin servicios reales."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from robot import booking


class CalendarFalso:
    def __init__(self, paginas):
        self.paginas = paginas
        self.consultas = []
        self.borrados = []

    def events(self):
        return self

    def list(self, **argumentos):
        self.consultas.append(argumentos)
        token = argumentos.get("pageToken")
        class Respuesta:
            def execute(otro):
                return self.paginas[token]
        return Respuesta()

    def delete(self, **argumentos):
        self.borrados.append(argumentos["eventId"])
        class Respuesta:
            def execute(otro):
                return {}
        return Respuesta()


def evento(evento_id, telefono, fecha):
    return {"id": evento_id, "summary": f"Cita Ana — {telefono}",
            "start": {"dateTime": fecha}}


class PulidoAgenda(unittest.TestCase):
    def setUp(self):
        booking._cache_huecos_invalidar()
        self.addCleanup(booking._cache_huecos_invalidar)

    def test_cancelar_consulta_todas_las_paginas_antes_de_elegir(self):
        fecha = "2026-12-01T09:00:00-07:00"
        servicio = CalendarFalso({None: {"items": [evento("uno", "521111", fecha)], "nextPageToken": "pagina2"},
                                  "pagina2": {"items": [evento("dos", "521111", fecha)]}})
        with patch.object(booking, "_servicio_calendar", return_value=servicio):
            with self.assertRaises(ValueError):
                booking.cancelar_cita("521111", fecha)
        self.assertEqual(servicio.borrados, [])
        self.assertEqual(len(servicio.consultas), 2)
        self.assertEqual(servicio.consultas[1]["pageToken"], "pagina2")

    def test_existe_no_confunde_telefono_hora_o_zona(self):
        fecha = "2026-12-01T09:00:00-07:00"
        servicio = CalendarFalso({None: {"items": [
            evento("telefono-ajeno", "999521111", fecha),
            evento("hora-ajena", "521111", "2026-12-01T09:00:00+00:00"),
            {"summary": "Recordatorio 521111", "start": {"dateTime": fecha}},
        ]}})
        with patch.object(booking, "_servicio_calendar", return_value=servicio):
            self.assertFalse(booking.existe_cita("521111", fecha))
            servicio.paginas[None]["items"].append(evento("propia", "521111", "2026-12-01T16:00:00+00:00"))
            self.assertTrue(booking.existe_cita("521111", fecha))

    def test_paginacion_con_token_repetido_falla_cerrada(self):
        servicio = CalendarFalso({None: {"items": [], "nextPageToken": "x"},
                                  "x": {"items": [], "nextPageToken": "x"}})
        with self.assertRaises(RuntimeError):
            booking._eventos_del_dia(servicio, datetime(2026, 12, 1, 16, tzinfo=timezone.utc))
        self.assertEqual(len(servicio.consultas), 2)
        self.assertTrue(servicio.consultas[0]["timeMin"].startswith("2026-12-01T00:00:00-07:00"))

    def test_cache_limitada_y_no_resucita_consulta_anterior_a_cambio(self):
        with patch.object(booking, "_HUECOS_CACHE_MAX", 2), patch.object(booking.time, "monotonic", side_effect=[1, 2, 3]):
            generacion = booking._HUECOS_CACHE_GENERACION
            for clave in ("a", "b", "c"):
                booking._cache_huecos_guardar(clave, [clave], generacion)
            self.assertEqual(set(booking._HUECOS_CACHE), {"b", "c"})
        generacion_anterior = booking._HUECOS_CACHE_GENERACION
        booking._cache_huecos_invalidar()
        booking._cache_huecos_guardar("resultado-obsoleto", ["hora"], generacion_anterior)
        self.assertEqual(booking._HUECOS_CACHE, {})

    def test_cache_de_profesionales_devuelve_copias(self):
        booking._cache_huecos_guardar("prof", [{"inicio": "a", "profesional": "Ana"}], booking._HUECOS_CACHE_GENERACION)
        copia, _ = booking._cache_huecos_leer("prof")
        copia[0]["profesional"] = "Alterado"
        nueva, _ = booking._cache_huecos_leer("prof")
        self.assertEqual(nueva[0]["profesional"], "Ana")

    def test_cantidad_cero_no_consulta_calendar(self):
        ahora = datetime(2026, 12, 1, 16, tzinfo=timezone.utc)
        with patch.object(booking, "_servicio_calendar") as servicio:
            self.assertEqual(booking.proximos_huecos_libres({1: (540, 1020)}, ahora, cantidad=0), [])
            self.assertEqual(booking.proximos_huecos_por_profesional([{"nombre": "Ana", "horarios": {}}], ahora, cantidad=0), [])
            servicio.assert_not_called()

    def test_borrado_incierto_invalida_cache(self):
        fecha = "2026-12-01T09:00:00-07:00"
        servicio = CalendarFalso({None: {"items": [evento("uno", "521111", fecha)]}})
        def borrar(**argumentos):
            class Respuesta:
                def execute(self):
                    raise TimeoutError("no se conoce el resultado")
            return Respuesta()
        servicio.delete = borrar
        booking._cache_huecos_guardar("a", [fecha], booking._HUECOS_CACHE_GENERACION)
        with patch.object(booking, "_servicio_calendar", return_value=servicio):
            with self.assertRaises(TimeoutError):
                booking.cancelar_cita("521111", fecha)
        self.assertEqual(booking._HUECOS_CACHE, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
