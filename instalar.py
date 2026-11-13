"""Instalador del robot (versión 2). Pregunta en español, paso a paso.

Uso:
    python instalar.py           # asistente interactivo, te pregunta todo
    python instalar.py --check   # solo revisa que todo esté en orden,
                                 # sin preguntar nada (para verificar)

Qué hace:
1. Revisa que tengas Python 3.10 o más.
2. Instala las librerías (pip install -r requirements.txt).
3. Te pregunta, una por una, tus claves (sin mostrarlas en pantalla
   mientras las escribes y sin volver a imprimirlas jamás).
4. Revisa que el archivo JSON de la cuenta de servicio de Google exista.
5. Escribe el archivo .env (si ya existe uno, te pregunta antes de
   tocarlo: nunca lo borra sin tu permiso).
6. Corre las pruebas simuladas y revisa que el servidor arranque.
7. Te dice, en español claro, los 3 pasos que siguen: desplegar,
   pegar el webhook en Meta y mandar el primer mensaje de prueba.

Se puede correr dos veces sin romper nada: la segunda vez solo te
pregunta si quieres reemplazar el .env que ya hiciste.

Nada de lo que escribas aquí se sube a ningún lado: las claves quedan
solo en tu archivo .env, en tu computadora.
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(RAIZ, ".env")
ENV_EXAMPLE = os.path.join(RAIZ, ".env.example")

# (clave en el .env, pregunta, ¿es secreta?, ¿obligatoria?)
PREGUNTAS = [
    ("GEMINI_API_KEY", "Tu clave gratis de Gemini (Google AI Studio, aistudio.google.com)", True, True),
    ("WHATSAPP_TOKEN", "Tu token de WhatsApp (Meta for Developers, el token del número)", True, True),
    ("WHATSAPP_PHONE_NUMBER_ID", "El Phone Number ID de WhatsApp (solo números, en Meta)", False, True),
    ("VERIFY_TOKEN", "Una palabra secreta que inventes para verificar el webhook (p. ej. robot-whatsapp-verifica)", False, True),
    ("OWNER_EMAIL", "El correo del dueño (ahí llegan los handoffs y el reporte semanal)", False, True),
    ("GMAIL_USER", "Tu correo de Gmail (el que manda los correos)", False, False),
    ("GMAIL_APP_PASSWORD", "La contraseña de aplicación de Gmail (no tu clave de Google)", True, False),
    ("GOOGLE_CREDENTIALS_JSON", "El archivo JSON de la cuenta de servicio de Google (p. ej. credenciales-google.json)", False, True),
    ("NEGOCIO_NOMBRE", "El nombre del negocio (opcional, Enter para saltarlo)", False, False),
]


def decir(texto: str) -> None:
    print(texto)


def correr(comando: list[str], descripcion: str) -> tuple[bool, str]:
    """Corre un comando y devuelve (salió bien, salida)."""
    try:
        resultado = subprocess.run(
            comando, cwd=RAIZ, capture_output=True, text=True, timeout=600
        )
        salida = (resultado.stdout + resultado.stderr).strip()
        return resultado.returncode == 0, salida
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def revisar_python() -> bool:
    """¿Tienes Python 3.10 o más?"""
    version = sys.version_info
    if version < (3, 10):
        decir(f"❌ Tu Python es {version.major}.{version.minor}. El robot necesita 3.10 o más.")
        decir("   Descarga uno nuevo en python.org y vuelve a correr: python instalar.py")
        return False
    decir(f"✓ Python {version.major}.{version.minor}.{version.micro} — bien.")
    return True


def revisar_archivos() -> bool:
    """¿Están los archivos que el robot necesita?"""
    faltan = []
    for nombre in ("requirements.txt", ".env.example", "app.py", "test_simulado.py", "test_v2.py", "test_v2_2.py", "test_v2_3.py", "test_v2_4.py", "test_v2_5.py", "test_v2_6.py"):
        if not os.path.exists(os.path.join(RAIZ, nombre)):
            faltan.append(nombre)
    if faltan:
        decir(f"❌ Faltan archivos en esta carpeta: {', '.join(faltan)}.")
        return False
    decir("✓ Archivos del robot completos.")
    return True


def instalar_librerias() -> bool:
    """pip install -r requirements.txt."""
    decir("Instalando las librerías (esto tarda un poco la primera vez)...")
    ok, salida = correr([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                        "instalar librerías")
    if not ok:
        decir("❌ No pude instalar las librerías. El error fue:")
        decir(salida[-1500:])
        decir("   Prueba a mano: pip install -r requirements.txt")
        return False
    decir("✓ Librerías instaladas.")
    return True


def revisar_env_example() -> bool:
    """¿El .env.example tiene todas las claves que el instalador pide?"""
    if not os.path.exists(ENV_EXAMPLE):
        decir("❌ Falta .env.example.")
        return False
    contenido = open(ENV_EXAMPLE, encoding="utf-8").read()
    faltan = [clave for clave, _, _, _ in PREGUNTAS if clave not in contenido]
    if faltan:
        decir(f"❌ En .env.example faltan: {', '.join(faltan)}.")
        return False
    decir("✓ .env.example tiene todas las claves.")
    return True


def probar_todo() -> bool:
    """py_compile + pruebas simuladas + el servidor arranca e importa."""
    ok, salida = correr([sys.executable, "-m", "py_compile", "app.py", "instalar.py",
                         "reporte_semanal.py", "test_simulado.py", "test_v2.py", "test_v2_2.py", "test_v2_3.py", "test_v2_4.py", "test_v2_5.py", "test_v2_6.py", "test_v2_7.py", "test_v2_8.py",
                         "robot/config.py", "robot/logic.py", "robot/whatsapp.py",
                         "robot/agrupar.py", "robot/ritmo.py", "robot/agent.py",
                         "robot/gemini.py", "robot/sheets.py", "robot/booking.py",
                         "robot/mail.py", "robot/report.py"],
                        "compilar")
    if not ok:
        decir("❌ Hay un error en el código (py_compile). El error fue:")
        decir(salida[-1500:])
        return False
    decir("✓ El código compila sin errores.")
    # (v2.7) Los modelos de Gemini deben ser vigentes: los retirados
    # (2.0-flash, 2.5-flash) dejaron al robot sin cerebro en noviembre
    # de 2026. Si el .env trae uno viejo, avisar antes de desplegar.
    ok, salida = correr(
        [sys.executable, "-c",
         "from robot.config import settings; "
         "retirados = {'gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.5-pro'}; "
         "malos = [m for m in (settings.gemini_model, settings.gemini_model_fallback) if m in retirados]; "
         "import sys; sys.exit('MODELOS RETIRADOS: ' + ', '.join(malos)) if malos else print('modelos Gemini vigentes: ' + settings.gemini_model + ' / ' + settings.gemini_model_fallback)"],
        "revisar modelos Gemini")
    if not ok:
        decir("❌ " + salida.strip().splitlines()[-1])
        decir("   Cambia GEMINI_MODEL a gemini-3.8-flash y GEMINI_MODEL_FALLBACK a gemini-3.6-flash.")
        return False
    decir("✓ " + salida.strip().splitlines()[-1])
    for prueba in ("test_simulado.py", "test_v2.py", "test_v2_2.py", "test_v2_3.py", "test_v2_4.py", "test_v2_5.py", "test_v2_6.py", "test_v2_7.py", "test_v2_8.py"):
        ok, salida = correr([sys.executable, prueba], f"correr {prueba}")
        ultima = salida.strip().splitlines()[-1] if salida.strip() else ""
        if not ok:
            decir(f"❌ {prueba} falló. Última línea: {ultima}")
            decir(salida[-1500:])
            return False
        decir(f"✓ {prueba}: {ultima}")
    ok, salida = correr([sys.executable, "-c", "import app; print(app.app.title)"],
                        "importar el servidor")
    if not ok:
        decir("❌ El servidor no arranca. El error fue:")
        decir(salida[-1500:])
        return False
    decir("✓ El servidor arranca (import app: ok).")
    return True


def preguntar(clave: str, pregunta: str, secreta: bool, obligatoria: bool) -> str:
    """Pregunta un valor. Las secretas no se ven al escribirlas."""
    while True:
        if secreta:
            valor = getpass.getpass(f"  {pregunta}: ").strip()
        else:
            valor = input(f"  {pregunta}: ").strip()
        if valor:
            return valor
        if obligatoria:
            decir("   Ese dato es obligatorio. Sin él, el robot no puede trabajar.")
        else:
            return ""


def escribir_env(valores: dict[str, str]) -> bool:
    """Escribe el .env. Si ya existe, pregunta antes de tocarlo."""
    if os.path.exists(ENV_PATH):
        respuesta = input("\nYa tienes un archivo .env. ¿Lo reemplazo con estos datos? (s/n): ").strip().lower()
        if respuesta not in ("s", "si", "sí", "y", "yes"):
            decir("No toqué tu .env. Si quieres cambiar un dato, ábrelo y edítalo a mano.")
            return False
    lineas = [
        "# Robot WhatsApp — claves del negocio. NUNCA subas este archivo.",
        "# Lo creó instalar.py. Si cambias de negocio, cambia solo los datos, no el código.",
        "",
    ]
    for clave in ("GOOGLE_SHEETS_ID", "GOOGLE_CREDENTIALS_JSON", "GEMINI_API_KEY",
                  "GEMINI_MODEL", "GEMINI_MODEL_FALLBACK", "WHATSAPP_TOKEN",
                  "WHATSAPP_PHONE_NUMBER_ID", "VERIFY_TOKEN", "OWNER_EMAIL",
                  "GMAIL_USER", "GMAIL_APP_PASSWORD", "CALENDAR_ID", "TIMEZONE",
                  "DURACION_CITA_MINUTOS", "PAUSA_HUMANO_HORAS", "REPORTE_DIA",
                  "REPORTE_HORA", "REPORTE_MINUTO", "NEGOCIO_NOMBRE",
                  "ESPERA_AGRUPAR_SEGUNDOS"):
        if clave in valores:
            lineas.append(f"{clave}={valores[clave]}")
    # Valores que el instalador no pregunta: se copian del ejemplo si no están.
    ejemplo = {}
    for linea in open(ENV_EXAMPLE, encoding="utf-8"):
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            ejemplo[k.strip()] = v.strip()
    for clave, valor in ejemplo.items():
        if clave not in valores and clave not in [l.split("=")[0] for l in lineas if "=" in l]:
            lineas.append(f"{clave}={valor}")
    with open(ENV_PATH, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas) + "\n")
    os.chmod(ENV_PATH, 0o600)  # Solo tú lo puedes leer.
    decir("✓ Archivo .env escrito (y con permiso solo para ti).")
    return True


def modo_check() -> int:
    """--check: revisa todo sin preguntar nada. Salida 0 = todo bien."""
    decir("Revisando el robot (modo --check, sin preguntas)...")
    bien = True
    bien = revisar_python() and bien
    bien = revisar_archivos() and bien
    bien = revisar_env_example() and bien
    bien = instalar_librerias() and bien
    bien = probar_todo() and bien
    if bien:
        decir("\n✓ Todo en orden. Puedes correr: python instalar.py")
        return 0
    decir("\n❌ Hay algo que arreglar (ver arriba).")
    return 1


def main() -> int:
    if "--check" in sys.argv:
        return modo_check()

    decir("=" * 60)
    decir("  Instalador del Robot WhatsApp (versión 2)")
    decir("  Te pregunto tus claves, una por una. Nada se muestra")
    decir("  en pantalla ni se sube a ningún lado.")
    decir("=" * 60)
    if not revisar_python():
        return 1
    if not revisar_archivos():
        return 1
    if not instalar_librerias():
        return 1

    decir("\nAhora tus datos. Tenlos a mano (ver README, pasos 2 a 5).")
    decir("Si no tienes uno todavía, pulsa Enter y te lo pedirá de nuevo.")
    decir("Para salir sin guardar nada: Ctrl+C.\n")
    valores: dict[str, str] = {}
    for clave, pregunta, secreta, obligatoria in PREGUNTAS:
        valor = preguntar(clave, pregunta, secreta, obligatoria)
        if clave == "OWNER_EMAIL" and valor and "@" not in valor:
            decir("   Eso no parece un correo (le falta @). Escríbelo de nuevo.")
            valor = preguntar(clave, pregunta, secreta, obligatoria)
        if clave == "GOOGLE_CREDENTIALS_JSON" and valor and not os.path.exists(valor) \
                and not os.path.exists(os.path.join(RAIZ, valor)):
            decir(f"   No encuentro ese archivo: {valor}")
            decir("   Tiene que ser el JSON que descargaste de Google Cloud (ver README, paso 3).")
            valor = preguntar(clave, pregunta, secreta, obligatoria)
        if valor:
            valores[clave] = valor

    if not escribir_env(valores):
        return 0  # El usuario no quiso reemplazar el .env: no es un error.

    decir("\nProbando que todo funcione...")
    if not probar_todo():
        decir("\nEl .env ya quedó guardado, pero las pruebas fallaron.")
        decir("Revisa el error de arriba y vuelve a correr: python instalar.py")
        return 1

    decir("\n" + "=" * 60)
    decir("  ¡Listo! Tu robot está instalado en tu computadora.")
    decir("=" * 60)
    decir("\nLo que sigue (3 pasos):")
    decir("  1. DESPLIEGA el robot para tener una dirección pública.")
    decir("     Lo más fácil: Render gratis (ver DESPLEGAR.md). Cuando")
    decir("     termine, Render te da una dirección como:")
    decir("       https://robot-whatsapp-xxxx.onrender.com")
    decir("     Tu webhook es esa dirección + /webhook:")
    decir("       https://robot-whatsapp-xxxx.onrender.com/webhook")
    decir("     Mientras pruebas en tu computadora, puedes usar ngrok:")
    decir("       ngrok http 8000  →  https://tu-url.ngrok.io/webhook")
    decir("  2. PEGA esa dirección en Meta for Developers, en WhatsApp")
    decir("     → Configuración del webhook, junto con tu VERIFY_TOKEN")
    decir("     (la palabra secreta que acabas de inventar). Meta te va")
    decir("     a pedir que verifiques: si el robot está prendido, pasa.")
    decir("  3. MANDA un mensaje de prueba al número de Meta y revisa")
    decir("     PROBARLO.md: el visto, el 'escribiendo...', la espera de")
    decir("     7 segundos si mandas varios mensajes, y los botones de")
    decir("     Confirmar / Cambiar hora / Hablar con una persona.")
    decir("\nPara arrancar el robot en tu computadora (pruebas):")
    decir("  uvicorn app:app --port 8000")
    decir("  y abre http://localhost:8000/health — debes ver {\"ok\": true}")
    decir("\nY recuerda: no hay recordatorios por WhatsApp en este robot.")
    decir("El reporte semanal llega solo por correo, los lunes a las 08:00.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
