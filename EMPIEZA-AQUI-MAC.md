# Empieza aquí — Mac, desde cero

No necesitas saber programar. Solo sigue los pasos en orden. Hoy solo haces
los pasos 1 a 4. Las claves (Gemini, WhatsApp, Google) son después, con el
instalador, y te lo explico paso a paso cuando llegues ahí.

## Paso 1. Descarga el robot

1. Descarga el archivo `robot-python.zip` que te mandó Muse.
2. Búscalo en Descargas y haz doble clic. Se crea una carpeta `robot-python`.
3. Arrástrala a tu Escritorio, para encontrarla fácil.

## Paso 2. Abre la Terminal

1. Aprieta `Cmd + Espacio` (la tecla de comando y la barra espaciadora).
2. Escribe `Terminal` y dale Enter.
3. Se abre una ventana negra. Ahí vas a pegar los comandos.

## Paso 3. Revisa que tengas Python

Pega esto en la Terminal y dale Enter:

```
python3 --version
```

- Si te dice `Python 3.10` o más (3.11, 3.12...), ya está, sigue al paso 4.
- Si te dice que no lo encuentra o tienes menos de 3.10, descárgalo de
  https://www.python.org/downloads/ — botón amarillo "Download Python",
  abre el instalador y dale a todo "Continuar". Luego cierra la Terminal,
  ábrela de nuevo y repite `python3 --version`.

## Paso 4. Entra a la carpeta y corre las pruebas

Pega una línea a la vez, dale Enter a cada una, espera a que termine:

```
cd ~/Desktop/robot-python
python3 instalar.py --check
```

Tienes que ver puros ✓ al final y "Todo en orden". Eso significa que el
robot está completo y que las 275 pruebas pasaron en tu Mac. No mandó ningún
mensaje, no gastó nada, solo se revisó a sí mismo.

Si quieres verlo por dentro, también puedes correr:

```
python3 test_simulado.py
python3 test_v2.py
```

## Paso 5. (Después, no hoy) El instalador de verdad

Cuando ya veas los ✓, corres:

```
python3 instalar.py
```

Te va a preguntar una por una tus claves, en español. No las muestra en
pantalla. Si todavía no tienes una clave, deja ese paso para luego: el
instalador te dice dónde sacarla, una por una.

## Si algo sale mal

Copia TODO lo que dice la Terminal (el comando que pegaste y el error en
rojo) y mándaselo a Muse. Con eso te dice exactamente qué hacer, no
adivines.

## El mapa completo (para que no te pierdas)

1. Hoy: pasos 1 a 4 de arriba. Solo ver que todo está en orden.
2. Luego: `python instalar.py` y sacar las claves gratis, una por una.
3. Luego: desplegarlo gratis en Render (guía en DESPLEGAR.md).
4. Luego: pegar la dirección del robot en Meta (WhatsApp) y mandar el
   primer mensaje de prueba.
