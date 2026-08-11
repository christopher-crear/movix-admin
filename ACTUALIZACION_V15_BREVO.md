# MOVIX V15 — Correos con Brevo en Render Free

Render Free bloquea los puertos SMTP habituales. Esta versión envía mensajes y
facturas por la API HTTPS de Brevo y mantiene SMTP como alternativa local.

## Variables obligatorias en Render

```env
EMAIL_PROVIDER=brevo
BREVO_API_KEY=TU_API_KEY_PRIVADA
BREVO_SENDER_EMAIL=movix_soporte@gmail.com
BREVO_SENDER_NAME=MOVIX
```

`BREVO_SENDER_EMAIL` debe coincidir exactamente con un remitente verificado en
Brevo. No agregues comillas ni espacios a la API Key y nunca la subas a GitHub.

Después de guardar las variables, ejecuta **Manual Deploy > Deploy latest
commit** en Render.

## Prueba

Desde el administrador abre **Mensajes a transportistas**, selecciona un
transportista con correo, deja activa la opción de enviar al correo y envía un
mensaje. El aviso se guarda primero en el buzón. Si Brevo lo rechaza, MOVIX
mostrará el motivo sin perder el mensaje interno.

Las facturas PDF utilizan la misma integración y se adjuntan en Base64.
