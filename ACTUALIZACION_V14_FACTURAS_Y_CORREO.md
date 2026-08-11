# MOVIX V14 · Facturas y correo

## Cambios incluidos

- Se eliminó el enlace **Ver factura** del historial de mensualidades. Ese
  historial queda dedicado únicamente a comprobantes y estados de pago.
- Se añadió **Mis facturas** al menú privado del transportista.
- El nuevo módulo permite buscar, filtrar por año, previsualizar y descargar
  cada factura PDF emitida al transportista autenticado.
- Las consultas siempre filtran por `driver_id`, por lo que un transportista no
  puede abrir facturas pertenecientes a otra cuenta.
- Se reorganizó la tarjeta administrativa de facturación con estado, requisitos,
  información de entrega y acciones separadas de vista previa y descarga.
- La respuesta del módulo **Solicitudes** ahora se envía directamente al correo
  del contacto mediante SMTP y queda registrada en la base de datos.
- Se documentó la configuración completa de Gmail mediante contraseña de
  aplicación para local y Render.

## Configuración necesaria

No se requiere una migración ni SQL adicional. Las facturas utilizan la tabla
existente `driver_invoices`.

Configura las variables `EMAIL_*` indicadas en `.env.example` y `README.md`. Para
Gmail, `EMAIL_HOST_PASSWORD` debe ser una contraseña de aplicación de 16
caracteres; la contraseña habitual de la cuenta no funciona con SMTP.

## Comprobación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```
