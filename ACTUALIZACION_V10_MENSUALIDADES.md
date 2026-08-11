# Actualización V10 · Mensualidades y documentos del transportista

## Antes de abrir el módulo

En Supabase abre **SQL Editor** y ejecuta una sola vez:

```text
sql/monthly_payments.sql
```

Después, en local:

```powershell
python manage.py migrate
python manage.py runserver
```

En Render no cambies el comando de inicio. Al subir esta versión, ejecuta el SQL
en Supabase y despliega el último commit. La migración Django `0004` solo
registra el modelo externo; la tabla real se crea con el SQL anterior.

## Nuevas direcciones

- Transportista: `/transportista/mensualidad/`
- Administrador: `/mensualidades/`

Ambas aparecen también en el menú lateral según el rol autenticado.

## Bloqueo en la aplicación móvil

El administrador cambia estos campos de `public.profiles`:

- `is_active=false`
- `blocked_at=<fecha y hora>`
- `blocked_reason=<motivo>`

La app móvil debe consultar `is_active` después del login y antes de aceptar una
carrera. Si es `false`, debe cerrar o limitar la sesión y mostrar
`blocked_reason`. El panel también crea una fila en `public.notifications` y,
cuando existe un token FCM activo, envía el aviso push.

## Pagos físicos

El comprobante en línea no es obligatorio. En **Pagos transportistas**, el
administrador puede pulsar **Pago físico** y la mensualidad del mes actual queda
registrada como aprobada sin archivo adjunto.
