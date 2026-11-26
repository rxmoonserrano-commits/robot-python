"""Ejecuta todas las baterías y exige también las conversaciones con Gemini.

Uso: python verificar_calidad.py
La batería real necesita GEMINI_API_KEY en el entorno o en .env. Una prueba
omitida, una dependencia ausente o una prueba fallida impiden marcar verde.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


RAIZ = Path(__file__).resolve().parent
LIMITE_LOCAL = 180
LIMITE_REAL = 1800


def main() -> int:
    pruebas = sorted(RAIZ.glob("test_*.py"))
    if not pruebas:
        print("ROJO: no se encontraron archivos de pruebas.")
        return 1
    entorno = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    fallidas = []
    aprobadas = 0
    for prueba in pruebas:
        limite = LIMITE_REAL if prueba.name == "test_conversaciones_doradas.py" else LIMITE_LOCAL
        try:
            resultado = subprocess.run(
                [sys.executable, "-B", str(prueba)], cwd=RAIZ, env=entorno,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=limite, check=False,
            )
        except subprocess.TimeoutExpired:
            fallidas.append(prueba.name)
            print(f"ROJO {prueba.name}: tiempo agotado ({limite} s)", flush=True)
            continue
        if resultado.returncode == 0:
            aprobadas += 1
            print(f"VERDE {prueba.name}", flush=True)
        else:
            fallidas.append(prueba.name)
            print(f"ROJO {prueba.name}: código {resultado.returncode}", flush=True)
            print(resultado.stdout[-4000:], flush=True)
    print(f"\nRESULTADO: {aprobadas}/{len(pruebas)} archivos aprobados; {len(fallidas)} fallidos o no ejecutados.")
    if fallidas:
        print("Pendientes: " + ", ".join(fallidas))
        return 1
    print("VERDE: todas las baterías terminaron correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
