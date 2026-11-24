# v3.20.0 — lista de subida (preparada 2026-11-23 ~15:21 MST)

## Estado real (verificado en esta corrida)

- **Local:** `app.py` VERSION = "3.20.0", `test_v3.py` espera 3.20.0, CHANGELOG trae la entrada v3.20.0 "Calidad conversacional: funciones 01, 04 y 05".
- **En vivo (Render):** sigue en **v3.19.0** — último keepalive 2026-11-23 22:17 UTC: `{"ok":true,"version":"3.19.0"}`.
- **GitHub (sync record):** última entrada es v3.19.0 commit `a6445aa7...` (39 entradas). **v3.20.0 NO está subido.**
- **Discrepancia a corregir:** `KIT-VENTA-CLIENTE.md` y `PROSPECCION-PRIMEROS-10.md` dicen "v3.20.0 en vivo en Render, verificado en /health y /estado" — eso hoy es falso. No usar esos textos con clientes hasta que el push + verificación en vivo pasen.

## Qué trae v3.20.0 (según CHANGELOG, trabajo hecho 21:39–21:43 UTC tras tu pedido de las 21:37 UTC)

- R10 en el revisor: respuesta entera repetida se reemplaza (antes solo el cierre).
- Historial en el prompt: últimos 8 mensajes (antes 5).
- Memoria útil: cita pasada se dice con servicio ("fue Blanqueamiento dental el ...").
- Guion: usar preferencias conocidas al proponer horario.
- Handoff con hilo: correo de alerta trae últimos 8 mensajes.
- Bug real corregido: "mejor no, quiero cambiarla" era tragado por la negación; ahora es cambiar. Negaciones faltantes cubiertas ("no me cambies la cita" ya no cambia nada).
- Tests: nueva `test_v3_20.py` (14 casos), 3 viajes nuevos en simulación conversacional (27 total), regresiones en `_intencion_cambio`. El CHANGELOG dice suite verde y 27/27; en este entorno de investigación no se pudieron re-correr (falta `dotenv`/`pytest`, ver abajo).

## Verificación hecha aquí

- `python3 -m compileall` sobre `robot/`, `app.py`, `test_v3_20.py`, `test_simulacion_conversacional.py`: **sin errores de sintaxis** (exit 0).
- `python3 test_v3_20.py`: **no corre en este entorno** — `ModuleNotFoundError: No module named 'dotenv'` (mismo límite ya registrado antes; las dependencias de Google no están instaladas aquí). La suite verde citada viene del trabajo reportado en CHANGELOG, no de una re-corrida en esta corrida.
- Versión consistente en `app.py` y `test_v3.py`: 3.20.0.

## Archivos a subir (manifest — excluir __pycache__, *.pyc, .DS_Store)

Cambiaron (mtime 21:39–21:43 UTC):
- `app.py`, `test_v3.py`
- `robot/logic.py`, `robot/revision.py`, `robot/agent.py`, `robot/mail.py`
- `test_v3_20.py` (nuevo), `test_simulacion_conversacional.py` (3 viajes nuevos)
- `test_v2_4.py`, `test_v2_5.py` (fallos reales del mismo bug de negación, según CHANGELOG)
- `CHANGELOG.md`, `README.md`, `guion-robot.md`
- `KIT-VENTA-CLIENTE.md`, `PROSPECCION-PRIMEROS-10.md` (solo después de corregir el "en vivo" o tras verificar el push)

Más el resto del árbol del repo como en pushes anteriores (sync record v3.19.0 lista ~83 archivos). Zip fresco v3.20.0: **ya generado** — `~/workspace/robot-python-v3.20.0.zip` (verificado 2026-11-23: `app.py` VERSION = "3.20.0", entrada CHANGELOG v3.20.0 presente).

## Pasos que quedan (para entrega, con tu aprobación del push)

1. Correr la suite completa en un entorno con dependencias (tu Mac o donde se corrió antes) y confirmar verde, en especial `test_v3_20.py` y la simulación conversacional 27/27.
2. Push a GitHub `rxmoonserrano-commits/robot-python` main con el manifest de arriba (una sola subida; la tarjeta de aprobación la apruebas tú — Jose tiene permiso permanente de subir, pero el push pide su tap).
3. Esperar redeploy en Render y verificar `/health` y `/estado` reportan **3.20.0**, salud true, cero errores.
4. Solo entonces: dejar el "en vivo" en KIT y PROSPECCION como está; si no, bajar esa frase a "v3.20.0 construido, pendiente de subir".
5. Generar zip fresco `robot-python-v3.20.0.zip` para tu Mac y registrar la entrada en el sync record.

## Pendientes relacionados (no bloquean el push)

- Recordatorios: siguen fallando cada hora (Diagnóstico 15:29–19:29 UTC hoy, 5 intentos, WhatsApp 404 template `recordatorio_cita` no existe en es_MX). Opción inmediata: poner `recordatorios=NO` en Configuración para silenciar el ruido hasta aprobar la plantilla en Meta.
- Contraseña de Gmail en Render (correos del dueño / reporte semanal).
- Batería dorada con IA real en tu Mac.
