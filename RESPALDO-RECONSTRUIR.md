# Respaldo y reconstrucción del robot (una página)

_Fecha: 2026-11-18. Explicación de Muse, sin prueba de reconstrucción en vivo todavía: es la guía para armarlo en minutos si algo se pierde._

## Dónde vive cada cosa

- **Código:** GitHub, repo `rxmoonserrano-commits/robot-python`. Si se borra la copia local, se clona de ahí.
- **Claves, tokens y APIs:** variables de entorno de Render (servicio `robot-whatsapp-python`) y tu `.env` en la Mac (`~/Desktop/robot-python/.env`). Nunca en el código.
- **Datos del negocio:** Google Sheet "Robot WhatsApp — Documento oficial", ID `1RfkuuvTf5f-YkhPkQnWzi0X95RpUoy3oHoDx00hFONo`.
- **WhatsApp / Meta:** el número, el webhook y la cuenta viven en los servidores de Meta, no en tu computadora.

## Lo único que hay que respaldar a mano

1. Tu `.env` de la Mac.
2. El archivo de credenciales de Google: `credenciales-google.json`.

Con esos dos archivos, más el código de GitHub, el robot se arma otra vez en minutos.

## Copiar y pegar en la Terminal de tu Mac (respaldo)

```bash
cd ~/Desktop/robot-python
cp .env ~/Desktop/respaldo-robot-env.txt
cp credenciales-google.json ~/Desktop/respaldo-robot-credenciales-google.json
```

Guarda esos dos archivos en un lugar seguro fuera de la carpeta del robot (por ejemplo en iCloud Drive o en un USB). No los subas a GitHub.

## Nombres de las variables en Render (solo los nombres, sin valores)

En Render → servicio `robot-whatsapp-python` → Environment, deben existir:

- `GEMINI_API_KEY`
- `WHATSAPP_TOKEN`
- `GOOGLE_SHEETS_ID`
- `GOOGLE_CREDENTIALS_JSON`
- `CALENDAR_ID`
- `ADMIN_TOKEN`
- `META_APP_SECRET`

Los valores se copian de tu `.env` / de Render actual; esta hoja no guarda ningún secreto.

## Datos de referencia (sin secretos)

- Hoja oficial: `1RfkuuvTf5f-YkhPkQnWzi0X95RpUoy3oHoDx00hFONo`
- Webhook: `https://robot-whatsapp-python.onrender.com/webhook`
- App webhook (Prueba Oficial): `3233605353503540`
- App Robot OG: `2964954367192962`
- Usuario del sistema con el token permanente: `ramon serrano`, ID `61596633213669` (negocio Inmobiliaria)

## Si hay que reconstruir desde cero

1. Clonar el repo de GitHub en la Mac.
2. Poner de vuelta `.env` y `credenciales-google.json` en la carpeta.
3. En Render, verificar que las variables de arriba sigan puestas y hacer Manual Deploy.
4. Correr la batería dorada:

```bash
cd ~/Desktop/robot-python
python3 test_conversaciones_doradas.py
```

5. Prueba de humo en WhatsApp: un "hola" y revisar visto / escribiendo.

## Pendiente honesto

La reconstrucción completa nunca se probó de principio a fin; esta hoja junta lo explicado el 2026-11-18. La primera vez que se haga un respaldo real, conviene anotar aquí qué faltó.
