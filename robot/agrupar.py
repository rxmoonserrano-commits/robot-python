"""Esperar y juntar mensajes (debounce / agregación).

El problema: un cliente manda 3 mensajes seguidos ("Hola", "Quiero una
cita", "Para el viernes en la mañana") y un robot tonto le contesta 3
veces. Una persona espera a que termines de escribir.

Cómo funciona:
- Cada mensaje que llega se guarda en un buzón por teléfono.
- Se prende un temporizador de ESPERA_AGRUPAR_SEGUNDOS (15 s por defecto).
- Si llega otro mensaje, el temporizador se reinicia (se espera de nuevo).
- Cuando pasan los 15 segundos sin que llegue nada, se procesan TODOS
  los mensajes juntos, en orden, como un solo texto para el agente.
- Si llega un mensaje mientras se está procesando un lote, se guarda
  como un lote nuevo y se procesa después, no se pierde ni se mezcla.
- Si Meta reenvía el mismo mensaje (mismo wamid), se ignora: no se
  contesta dos veces lo mismo. Los wamids ya vistos viven en memoria
  (para guardarlos para siempre haría falta una base de datos; eso es
  una mejora futura, ver README).

El webhook solo mete el mensaje en el buzón y devuelve 200 enseguida;
el trabajo pesado (Gemini, Sheets) pasa en segundo plano, en el hilo
del temporizador. Así Meta nunca espera.
"""

from __future__ import annotations

import json
import os
import threading
import time

# Cuántos wamids se guardan en memoria antes de limpiar la lista.
# Un negocio chico no llega a esto en meses; es solo para que la
# memoria no crezca sin freno si el robot corre años.
_MAX_VISTOS = 5000


class Agrupador:
    """Buzón por teléfono con temporizador. Hilo-seguro."""

    def __init__(self, callback, espera_segundos: float = 15.0, archivo: str | None = None,
                 atascado_segundos: float = 300.0):
        """callback(telefono, nombre, textos, wamids): qué hacer con el lote.

        textos: lista de textos en orden. wamids: sus ids de WhatsApp.
        archivo: si se da, el buzón se guarda ahí en disco (lotes
        pendientes + wamids ya vistos) cada vez que cambia, y se
        recupera con cargar(). (v3.0) Antes todo vivía solo en
        memoria: si el servidor se reiniciaba a mitad de un lote,
        esos mensajes se perdían (Meta ya había recibido el 200).
        El archivo es un respaldo, no una base de datos: un despliegue
        nuevo lo borra, pero un reinicio del mismo despliegue no.
        atascado_segundos: (v3.4) si un lote lleva más que esto en
        proceso, se da por muerto y el teléfono se libera: sin esto,
        un atasco deja a ese cliente mudo para siempre (sus lotes
        nuevos se re-encolan cada 2 s sin fin, sin aviso y sin fila).
        """
        self.callback = callback
        self.espera_segundos = espera_segundos
        self.archivo = archivo
        self.atascado_segundos = atascado_segundos
        self._candado = threading.Lock()
        self._pendientes: dict[str, dict] = {}
        self._vistos: set[str] = set()
        # Teléfono -> momento (monotonic) en que empezó su lote.
        self._procesando: dict[str, float] = {}

    def pendientes(self) -> int:
        """Cuántos teléfonos tienen un lote esperando (para /estado)."""
        with self._candado:
            return sum(1 for b in self._pendientes.values() if b["textos"])

    def procesando(self) -> int:
        """Cuántos teléfonos tienen un lote en proceso (para /estado)."""
        with self._candado:
            return len(self._procesando)

    def _guardar(self) -> None:
        """Escribe el buzón en disco (escritura atómica). Best-effort."""
        if not self.archivo:
            return
        try:
            with self._candado:
                datos = {
                    "pendientes": {
                        tel: {"textos": list(b["textos"]), "wamids": list(b["wamids"]),
                              "nombre": b["nombre"]}
                        for tel, b in self._pendientes.items()
                    },
                    "vistos": list(self._vistos)[:_MAX_VISTOS],
                }
            tmp = self.archivo + ".tmp"
            with open(tmp, "w", encoding="utf-8") as archivo:
                json.dump(datos, archivo)
            os.replace(tmp, self.archivo)
        except Exception:
            pass  # el buzón en disco es un respaldo; el de memoria sigue

    def cargar(self) -> int:
        """Recupera del disco los lotes que quedaron pendientes.

        Se llama al arrancar el servidor (no en __init__, para que
        importar el módulo no procese mensajes solo). Cada lote
        recuperado se procesa cuando se acabe la espera, como si
        acabara de llegar. Devuelve cuántos lotes se recuperaron.
        """
        if not self.archivo or not os.path.exists(self.archivo):
            return 0
        try:
            with open(self.archivo, encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except Exception:
            return 0
        restaurados = 0
        with self._candado:
            for telefono, buzon in (datos.get("pendientes") or {}).items():
                if not buzon.get("textos"):
                    continue
                self._pendientes[telefono] = {
                    "textos": list(buzon["textos"]),
                    "wamids": list(buzon.get("wamids", [])),
                    "nombre": buzon.get("nombre", ""),
                    "timer": None,
                }
                timer = threading.Timer(self.espera_segundos, self._disparar, args=(telefono,))
                timer.daemon = True
                self._pendientes[telefono]["timer"] = timer
                timer.start()
                restaurados += 1
            for wamid in (datos.get("vistos") or []):
                self._vistos.add(wamid)
        return restaurados

    def agregar(self, telefono: str, texto: str, wamid: str = "", nombre: str = "") -> bool:
        """Mete un mensaje en el buzón. Devuelve False si es un duplicado.

        Devuelve True si se guardó (aunque todavía no se procese).
        """
        with self._candado:
            if wamid:
                if wamid in self._vistos:
                    return False  # Meta lo reenvió: no contestar dos veces.
                self._vistos.add(wamid)
                if len(self._vistos) > _MAX_VISTOS:
                    self._vistos.clear()
                    self._vistos.add(wamid)
            buzon = self._pendientes.get(telefono)
            if buzon is None:
                buzon = {"textos": [], "wamids": [], "nombre": nombre, "timer": None}
                self._pendientes[telefono] = buzon
            if nombre:
                buzon["nombre"] = nombre
            buzon["textos"].append(texto)
            if wamid:
                buzon["wamids"].append(wamid)
            # Reiniciar el temporizador: se espera desde el ÚLTIMO mensaje.
            if buzon["timer"] is not None:
                buzon["timer"].cancel()
            timer = threading.Timer(self.espera_segundos, self._disparar, args=(telefono,))
            timer.daemon = True
            buzon["timer"] = timer
            timer.start()
        self._guardar()
        return True

    def procesar_ahora(self, telefono: str) -> bool:
        """Procesa el buzón de un teléfono ya, sin esperar. Para pruebas.

        Devuelve True si había algo que procesar.
        """
        with self._candado:
            buzon = self._pendientes.get(telefono)
            if not buzon or not buzon["textos"]:
                return False
            if buzon["timer"] is not None:
                buzon["timer"].cancel()
        self._disparar(telefono)
        return True

    def _disparar(self, telefono: str) -> None:
        """El temporizador se acabó: sacar el lote y procesarlo."""
        with self._candado:
            if telefono in self._procesando:
                # (v3.4) Si el lote anterior lleva demasiado sin terminar,
                # se da por muerto y se libera: el teléfono no se queda
                # mudo para siempre. El lote atascado ya no se recupera;
                # lo que importa es que el siguiente sí se atienda.
                if time.monotonic() - self._procesando[telefono] > self.atascado_segundos:
                    del self._procesando[telefono]
                else:
                    # Todavía se está procesando el lote anterior: esperar 2 s
                    # más y volver a intentar (los mensajes nuevos ya están
                    # guardados en el buzón como lote nuevo).
                    buzon = self._pendientes.get(telefono)
                    if buzon and buzon["textos"]:
                        timer = threading.Timer(2.0, self._disparar, args=(telefono,))
                        timer.daemon = True
                        buzon["timer"] = timer
                        timer.start()
                    return
            buzon = self._pendientes.pop(telefono, None)
            if not buzon or not buzon["textos"]:
                return
            self._procesando[telefono] = time.monotonic()
            textos, wamids, nombre = buzon["textos"], buzon["wamids"], buzon["nombre"]
        self._guardar()
        try:
            self.callback(telefono, nombre, textos, wamids)
        finally:
            with self._candado:
                self._procesando.pop(telefono, None)
