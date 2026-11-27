"""Regresiones de posiciones reales en hojas con filas vacías; servicios falsos."""
import unittest
from unittest.mock import patch

from robot import sheets
from test_auditoria_datos import _ServicioFalso, _ENCABEZADOS_CITAS, _fila_citas_base, TEL


class PulidoSheets(unittest.TestCase):
    def setUp(self):
        sheets._CACHE.clear()
        self.addCleanup(sheets._CACHE.clear)

    def test_clientes_tras_hueco_mantiene_posicion_y_cache_aislada(self):
        encabezados = list(sheets._COLUMNAS_CLIENTES)
        fila = ["" for _ in encabezados]
        fila[encabezados.index("telefono")] = TEL
        servicio = _ServicioFalso(datos_get={"values": [encabezados, [], fila]})
        with patch.object(sheets, "_servicio_sheets", return_value=servicio):
            copia = sheets.leer_pestana("Clientes")
            copia[0]["telefono"] = "otro"
            self.assertEqual(sheets._fila_cliente_por_telefono(TEL)[0], 3)
            sheets.cancelar_cita_cliente(TEL)
        self.assertEqual(servicio.valores.updates[0]["range"], "Clientes!E3:G3")
        self.assertEqual(servicio.valores.gets[0], "Clientes!A:Z")

    def test_propuesta_tras_fila_borrada_actualiza_y_borra_su_fila(self):
        encabezados = list(sheets._COLUMNAS_PROPUESTA)
        fila = [TEL] + ["" for _ in encabezados[1:]]
        servicio = _ServicioFalso(datos_get={"values": [encabezados, [], fila]})
        with patch.object(sheets, "_servicio_sheets", return_value=servicio):
            sheets.guardar_propuesta(TEL, {})
            sheets.borrar_propuesta(TEL)
        self.assertEqual(servicio.valores.updates[0]["range"], "Propuestas!A3:I3")
        self.assertEqual(servicio.clears, ["Propuestas!A3:I3"])

    def test_citas_tras_fila_vacia_actualiza_fila_correcta(self):
        servicio = _ServicioFalso(datos_get={"values": [_ENCABEZADOS_CITAS, [], _fila_citas_base()]})
        with patch.object(sheets, "_servicio_sheets", return_value=servicio):
            sheets.actualizar_cita_espejo(TEL, "2026-11-23", estado="Cancelada")
        self.assertEqual(servicio.valores.updates[0]["range"], "Citas!F3:P3")

    def test_datos_despues_de_10000_son_visibles(self):
        valores = [["telefono"]] + [[str(i)] for i in range(10001)]
        servicio = _ServicioFalso(datos_get={"values": valores})
        with patch.object(sheets, "_servicio_sheets", return_value=servicio):
            self.assertEqual(sheets.leer_pestana("Clientes")[-1]["telefono"], "10000")
        self.assertEqual(servicio.valores.gets, ["Clientes!A:Z"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
