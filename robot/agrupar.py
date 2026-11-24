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
- (v3.20.4) Orden por timestamp: el webhook lanza un hilo por
  mensaje, así que dos mensajes del mismo cliente pueden entrar al
  buzón desordenados. Cada entrada guarda el timestamp que manda
  WhatsApp y el lote se despacha ordenado por ese timestamp (sin
  timestamp se conserva el orden de llegada). Así "no, mejor el
  miércoles" nunca queda antes de "quiero el martes" por una
  carrera de hilos.
- (v3.20.4) marcar_visto(wamid): registra un wamid como visto y
  devuelve False si ya estaba. Lo usan los botones y las respuestas
  directas, que no pasan por el buzón: sin esto, un reenvío de Meta
  atendía el mismo tap dos veces (p. ej. dos correos de handoff).

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
                 atascado_segundos: float = 300.0, max_vistos: int = _MAX_VISTOS):
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
        max_vistos: (v3.20.3) cuántos wamids se recuerdan para
        ignorar reenvíos de Meta. Al pasar el tope se desalojan los
        MÁS VIEJOS (FIFO), no todos: antes se borraban todos y un
        reenvío viejo se reprocesaba (respuesta duplicada).
        """
        self.callback = callback
        self.espera_segundos = espera_segundos
        self.archivo = archivo
        self.atascado_segundos = atascado_segundos
        self.max_vistos = max(1, int(max_vistos))
        self._candado = threading.Lock()
        self._pendientes: dict[str, dict] = {}
        # (v3.20.4) Contador de llegada: desempata el orden cuando
        # dos entradas traen el mismo timestamp (o ninguno).
        self._seq = 0
        # dict como conjunto ordenado (Python 3.7+): las claves salen
        # en orden de inserción, así el desalojo es FIFO.
        self._vistos: dict[str, None] = {}
        # Teléfono -> momento (monotonic) en que empezó su lote.
        self._procesando: dict[str, float] = {}

    def pendientes(self) -> int:
        """Cuántos teléfonos tienen un lote esperando (para /estado)."""
        with self._candado:
            return sum(1 for b in self._pendientes.values() if b["entradas"])

    def _registrar_visto(self, wamid: str) -> bool:
        """(Con el candado tomado) Marca un wamid como visto.

        Devuelve False si ya estaba (Meta lo reenvió). Al pasar el
        tope se desalojan los más viejos (FIFO), nunca todos.
        """
        if wamid in self._vistos:
            return False
        self._vistos[wamid] = None
        while len(self._vistos) > self.max_vistos:
            self._vistos.pop(next(iter(self._vistos)))
        return True

    def marcar_visto(self, wamid: str) -> bool:
        """Registra un wamid como visto. False si ya estaba.

        Para los caminos que NO pasan por el buzón (botones,
        respuestas directas): sin esto, un reenvío de Meta atendía
        el mismo mensaje dos veces. (v3.20.4)
        """
        if not wamid:
            return True
        with self._candado:
            nuevo = self._registrar_visto(wamid)
        if nuevo:
            self._guardar()
        return nuevo

    @staticmethod
    def _clave_orden(entrada):
        """Clave de orden del lote: por timestamp de WhatsApp.

        Las entradas sin timestamp van al final, en orden de
        llegada (compatibilidad con llamadas viejas sin timestamp).
        """
        ts, seq = entrada[0], entrada[1]
        if ts is None:
            return (1, 0.0, seq)
        return (0, ts, seq)

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
                        tel: {"entradas": [list(e) for e in b["entradas"]],
                              "nombre": b["nombre"]}
                        for tel, b in self._pendientes.items()
                    },
                    "vistos": list(self._vistos)[:self.max_vistos],
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
                # (v3.20.4) Formato nuevo: entradas [ts, seq, texto,
                # wamid]. Formato viejo (v3.20.3 y antes): textos +
                # wamids sueltos; se cargan sin timestamp, en orden.
                if buzon.get("entradas") is not None:
                    entradas = []
                    for e in buzon["entradas"]:
                        e = list(e) + ["", "", ""][: max(0, 4 - len(e))]
                        entradas.append([e[0], int(e[1] or 0), e[2], e[3]])
                else:
                    textos = buzon.get("textos") or []
                    wamids = buzon.get("wamids") or []
                    entradas = [
                        [None, i, t, (wamids[i] if i < len(wamids) else "")]
                        for i, t in enumerate(textos)
                    ]
                if not entradas:
                    continue
                self._pendientes[telefono] = {
                    "entradas": entradas,
                    "nombre": buzon.get("nombre", ""),
                    "timer": None,
                }
                self._seq = max(self._seq, max(e[1] for e in entradas) + 1)
                timer = threading.Timer(self.espera_segundos, self._disparar, args=(telefono,))
                timer.daemon = True
                self._pendientes[telefono]["timer"] = timer
                timer.start()
                restaurados += 1
            for wamid in (datos.get("vistos") or []):
                self._vistos[wamid] = None
        return restaurados

    def agregar(self, telefono: str, texto: str, wamid: str = "", nombre: str = "",
                timestamp=None) -> bool:
        """Mete un mensaje en el buzón. Devuelve False si es un duplicado.

        Devuelve True si se guardó (aunque todavía no se procese).

        timestamp: (v3.20.4) el timestamp que manda WhatsApp (segundos
        desde epoch). El lote se despacha ordenado por este valor, no
        por el orden en que los hilos del webhook alcanzaron el
        candado. Sin timestamp, se conserva el orden de llegada.
        """
        try:
            ts = float(timestamp) if timestamp not in (None, "") else None
        except (TypeError, ValueError):
            ts = None
        with self._candado:
            if wamid:
                if not self._registrar_visto(wamid):
                    return False  # Meta lo reenvió: no contestar dos veces.
            buzon = self._pendientes.get(telefono)
            if buzon is None:
                buzon = {"entradas": [], "nombre": nombre, "timer": None}
                self._pendientes[telefono] = buzon
            if nombre:
                buzon["nombre"] = nombre
            buzon["entradas"].append([ts, self._seq, texto, wamid])
            self._seq += 1
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
            if not buzon or not buzon["entradas"]:
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
                    if buzon and buzon["entradas"]:
                        timer = threading.Timer(2.0, self._disparar, args=(telefono,))
                        timer.daemon = True
                        buzon["timer"] = timer
                        timer.start()
                    return
            buzon = self._pendientes.pop(telefono, None)
            if not buzon or not buzon["entradas"]:
                return
            self._procesando[telefono] = time.monotonic()
            # (v3.20.4) El lote sale ordenado por el timestamp de
            # WhatsApp, no por el orden en que los hilos del webhook
            # alcanzaron el candado.
            entradas = sorted(buzon["entradas"], key=self._clave_orden)
            textos = [e[2] for e in entradas]
            wamids = [e[3] for e in entradas if e[3]]
            nombre = buzon["nombre"]
        self._guardar()
        try:
            self.callback(telefono, nombre, textos, wamids)
        finally:
            with self._candado:
                self._procesando.pop(telefono, None)
