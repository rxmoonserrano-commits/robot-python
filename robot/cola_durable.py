"""Almacenamiento de mensajes de Meta en Google Sheets.

Contrato: una sola instancia de la aplicación escribe la pestaña BuzonMeta;
el dueño no debe editarla. Cada fila permanece allí después de completarse
para que un reintento posterior conserve el mismo ID. No hay transacciones
entre Sheets, Meta y Calendar: un corte tras un efecto externo y antes de
marcar la fila puede requerir reconciliación.

Esta clase implementa el almacenamiento; no arranca hilos por sí sola.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from .config import settings
from .sheets import _servicio_sheets


class ColaDurable:
    """Buzón serializado en Sheets para un servicio de un solo proceso."""

    PESTANA = "BuzonMeta"
    ENCABEZADOS = ["id_meta", "estado", "recibido_en", "contenido"]
    PENDIENTE = "PENDIENTE"
    TERMINADO = "TERMINADO"
    TAMANO_PAGINA = 250

    def __init__(self, servicio: Callable[[], Any] = _servicio_sheets,
                 sheet_id: str | None = None):
        self.servicio = servicio
        self.sheet_id = sheet_id or settings.sheet_id
        self._candado = threading.RLock()

    def _valores(self, rango: str) -> list[list]:
        return (self.servicio().values().get(
            spreadsheetId=self.sheet_id, range=rango,
        ).execute().get("values") or [])

    def _validar_pestana(self) -> None:
        encabezados = self._valores(f"{self.PESTANA}!A1:D1")
        if not encabezados or encabezados[0] != self.ENCABEZADOS:
            raise RuntimeError("BuzonMeta no existe o sus encabezados son incorrectos")

    def _filas(self):
        """Itera páginas acotadas conservando el número real de fila."""
        inicio = 2
        while True:
            fin = inicio + self.TAMANO_PAGINA - 1
            valores = self._valores(f"{self.PESTANA}!A{inicio}:D{fin}")
            for indice, fila in enumerate(valores):
                yield inicio + indice, list(fila)
            if len(valores) < self.TAMANO_PAGINA:
                return
            inicio += self.TAMANO_PAGINA

    def guardar(self, mensajes: list[tuple[dict, dict]]) -> int:
        """Persiste mensajes no vistos antes de confirmar el webhook.

        Lanza ante cualquier error de Sheets o mensaje sin ID. Se realiza
        un solo append por webhook; si su resultado es incierto, el
        siguiente reintento vuelve a leer IDs antes de intentar escribir.
        """
        candidatos = []
        for mensaje, valor in mensajes:
            if not isinstance(mensaje, dict) or not isinstance(valor, dict):
                raise ValueError("Formato de mensaje inválido")
            wamid = str(mensaje.get("id") or "").strip()
            if not wamid:
                raise ValueError("Mensaje sin ID de Meta")
            telefono = str(mensaje.get("from") or "").strip()
            if not telefono:
                raise ValueError("Mensaje sin remitente")
            # El perfil se usa solo para obtener el nombre del remitente;
            # no guardar contactos de terceros ni atributos adicionales.
            contactos = valor.get("contacts")
            contactos = contactos if isinstance(contactos, list) else []
            perfil = []
            for contacto in contactos:
                if not isinstance(contacto, dict) or str(contacto.get("wa_id") or "") != telefono:
                    continue
                datos_perfil = contacto.get("profile")
                nombre = datos_perfil.get("name", "") if isinstance(datos_perfil, dict) else ""
                perfil.append({"wa_id": telefono, "profile": {"name": str(nombre or "")}})
                break
            contenido = json.dumps({"mensaje": mensaje, "contacts": perfil},
                                   ensure_ascii=False, separators=(",", ":"))
            if len(contenido) > 45000:
                raise ValueError("Mensaje demasiado grande para una celda de Sheets")
            candidatos.append((wamid, contenido))
        if not candidatos:
            return 0
        with self._candado:
            self._validar_pestana()
            buscados = {wamid for wamid, _ in candidatos}
            conocidos = set()
            for _, fila in self._filas():
                if fila and str(fila[0]) in buscados:
                    conocidos.add(str(fila[0]))
                    if conocidos == buscados:
                        break
            ahora = datetime.now(timezone.utc).isoformat()
            nuevas = []
            for wamid, contenido in candidatos:
                if wamid not in conocidos:
                    nuevas.append([wamid, self.PENDIENTE, ahora, contenido])
                    conocidos.add(wamid)
            if nuevas:
                self.servicio().values().append(
                    spreadsheetId=self.sheet_id, range=f"{self.PESTANA}!A:D",
                    valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                    body={"values": nuevas},
                ).execute()
            return len(nuevas)

    def pendientes(self, limite: int = 50, excluir_telefonos: set[str] | None = None) -> list[tuple[int, str, dict]]:
        """Consulta pendientes por páginas, sin cargar toda la hoja en memoria."""
        if limite <= 0:
            return []
        excluir = excluir_telefonos or set()
        encontrados = []
        with self._candado:
            self._validar_pestana()
            for numero, fila in self._filas():
                if len(fila) < 4 or fila[1] != self.PENDIENTE:
                    continue
                try:
                    contenido = json.loads(fila[3])
                    if not isinstance(contenido, dict) or not isinstance(contenido.get("mensaje"), dict):
                        raise ValueError("Contenido inválido")
                except (ValueError, TypeError):
                    # Se deja pendiente para revisión sin bloquear a los demás.
                    from .registro import aviso
                    aviso(f"[cola] Fila {numero} ilegible; requiere revisión")
                    continue
                if str(contenido["mensaje"].get("from") or "") in excluir:
                    continue
                contenido["_recibido_en"] = str(fila[2])
                encontrados.append((numero, str(fila[0]), contenido))
                if len(encontrados) >= limite:
                    break
        return encontrados

    def siguiente(self) -> tuple[int, str, dict] | None:
        """Primer mensaje pendiente; consulta las filas en orden, por páginas."""
        pendientes = self.pendientes(limite=1)
        return pendientes[0] if pendientes else None

    def terminar(self, numero: int, wamid: str) -> None:
        self.terminar_lote([(numero, wamid)])

    def terminar_lote(self, filas: list[tuple[int, str]]) -> None:
        """Completa el lote en una escritura, verificando cada ID antes."""
        if not filas:
            return
        with self._candado:
            for numero, wamid in filas:
                if numero < 2:
                    raise ValueError("Número de fila inválido")
                fila = self._valores(f"{self.PESTANA}!A{numero}:B{numero}")
                if not fila or not fila[0] or str(fila[0][0]) != wamid:
                    raise RuntimeError("La fila del buzón cambió; no se puede completar")
            self.servicio().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={"valueInputOption": "RAW", "data": [
                    {"range": f"{self.PESTANA}!B{numero}", "values": [[self.TERMINADO]]}
                    for numero, _ in filas
                ]},
            ).execute()
