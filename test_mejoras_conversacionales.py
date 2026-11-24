"""Mejoras conversacionales de la auditoría (v3.20.9).

Cubre la aplicación del reporte de auditoría conversacional
(~/workspace/auditoria-conversacional-notas.md):
- G4 afinado: con propuesta pendiente + pregunta nueva, el
  recordatorio mantiene el bucle abierto SIN repetir día/hora.
- Mejoras aditivas de marketing/ventas/psicología/PNL (§2.3):
  presuposición suave, espejo de lenguaje, prueba social solo si
  está en Conocimiento, ejemplo de objeción de precio, pequeños
  síes, despedida sin agendar y lenguaje sensorial tranquilo.
- Bloque "Ejemplos de ritmo" en guion-robot.md (§2.1c).
- Sincronización (§3.3): las frases clave deben existir en AMBOS
  archivos (robot/agent.py y guion-robot.md); un cambio en un solo
  archivo rompe este test y obliga a sincronizar.

Uso:  python3 test_mejoras_conversacionales.py
Salida: 0 = todo ok; 1 = algún caso falló (se imprime el caso exacto).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTADOS = []


def caso(nombre, fn):
    try:
        ok, msg = fn()
    except Exception as e:  # noqa: BLE001
        ok, msg = False, f"excepción: {e!r}"
    RESULTADOS.append((nombre, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {nombre}" + ("" if ok else f" — {msg}"))


def _leer(rel):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), rel),
              encoding="utf-8") as f:
        return f.read()


def _norm(texto):
    """Colapsa saltos de línea y espacios para comparar frases partidas."""
    import re
    return re.sub(r"\s+", " ", texto)


def _ambos():
    return (_norm(_leer("robot/agent.py")), _norm(_leer("guion-robot.md")))


# --- A. Sincronización: frases clave en ambos archivos (§3.3) ---

FRASES_CLAVE = [
    # G7: la regla de nunca deflectar sin precios (etapa pregunto).
    'NUNCA respondas "¿cuál te interesa?"',
    # G7: la misma regla en el playbook.
    'Nunca deflectes con "¿cuál te interesa?"',
    # G4: recordatorio sin repetir la hora.
    "sigue en pie, sin compromiso",
    "sin mencionar de nuevo la hora",
    # §2.3a presuposición suave.
    "elección suave",
    # §2.3b espejo de lenguaje.
    "Usa las palabras del cliente",
    # §2.3c prueba social solo si está en Conocimiento.
    "Prueba social",
    # §2.3d ejemplo de objeción de precio.
    "vale la pena porque incluye",
    # §2.3e pequeños síes.
    "Cada sí pequeño",
    # §2.3f despedida sin agendar.
    "Se despide sin agendar",
    # §2.3g lenguaje sensorial tranquilo.
    "lenguaje sensorial tranquilo",
]


def a1():
    agente, espejo = _ambos()
    faltan = [f for f in FRASES_CLAVE if f not in agente or f not in espejo]
    return (not faltan), f"frases sin sincronizar: {faltan}"


# --- B. Bloque Ejemplos de ritmo en guion-robot.md (§2.1c) ---

def b1():
    espejo = _leer("guion-robot.md")
    ok = ("## Ejemplos de ritmo" in espejo
          and "¿qué servicios tienen?" in espejo
          and "blanqueamiento dental ($1,800" in espejo)
    return ok, "falta el bloque Ejemplos de ritmo o el ejemplo de servicios con precios"


# --- C. G4: texto viejo reemplazado ---

def c1():
    espejo = _leer("guion-robot.md")
    ok = "recuerda en una frase corta que los horarios quedaron arriba" not in espejo
    return ok, "sigue el texto viejo de oferta_pendiente en guion-robot.md"


def c2():
    agente = _leer("robot/agent.py")
    ok = ("NO repitas la oferta ni menciones de nuevo el" in agente
          and "NO repitas la oferta. Si hace falta, recuérdala" not in agente)
    return ok, "el texto viejo de oferta_pendiente sigue en agent.py"


def main():
    caso("A1 frases clave sincronizadas en agent.py y guion-robot.md", a1)
    caso("B1 bloque Ejemplos de ritmo en guion-robot.md", b1)
    caso("C1 texto viejo de G4 fuera de guion-robot.md", c1)
    caso("C2 texto viejo de G4 fuera de agent.py", c2)
    fallos = [n for n, ok in RESULTADOS if not ok]
    print(f"\n{len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos ok "
          f"(mejoras conversacionales)")
    if fallos:
        print("Fallos:")
        for n in fallos:
            print(f"  - {n}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
