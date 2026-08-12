# MOVIX V17 · bloqueo, Google, notificaciones y pago físico

## 1. Ejecutar en Supabase

Abre **Supabase → SQL Editor**, copia todo el contenido de:

`sql/010_account_blocks_and_notification_links.sql`

y pulsa **Run**. Esta migración:

- agrega `profiles.is_blocked` y lo sincroniza con `is_active`;
- impide que una cuenta bloqueada cree o modifique carreras, reseñas, pagos y tokens;
- permite que cada usuario elimine solamente sus propias notificaciones;
- agrega la función RPC `dismiss_notification`.

En Render no necesitas ejecutar `python manage.py migrate` por este modelo no administrado, pero el archivo `build.sh` puede seguir ejecutándolo para las tablas internas de Django.

## 2. Deslizar para eliminar en Flutter

La interfaz móvil debe llamar a Supabase al confirmar el gesto:

```dart
Dismissible(
  key: ValueKey(notification.id),
  direction: DismissDirection.endToStart,
  confirmDismiss: (_) async {
    await Supabase.instance.client.rpc(
      'dismiss_notification',
      params: {'notification_id': notification.id},
    );
    return true;
  },
  child: NotificationCard(notification: notification),
)
```

La política SQL impide borrar notificaciones ajenas. En el buzón web del transportista el gesto y el botón de eliminar ya están implementados.

## 3. Bloqueo real

El botón del panel ahora actualiza simultáneamente:

- `is_active = false`
- `is_blocked = true`
- `blocked_reason`
- `blocked_at`

La app debe ocultar o desactivar acciones cuando `profiles.is_blocked` sea verdadero. Las políticas RLS son la segunda protección y rechazan la escritura incluso si el usuario conserva un JWT anterior.

## 4. Registro con Google

Si Google devuelve `user_metadata.avatar_url` o `picture`, MOVIX lo utiliza automáticamente y no pide otra foto de perfil. Si Google no devuelve imagen, la foto tipo carnet sigue siendo obligatoria. Las fotografías que el transportista ya haya subido manualmente nunca se reemplazan.

## 5. Pago físico y factura

En **Pagos de transportistas → Pago físico** se abre una ventana con transportista, mes y valor. Al guardar:

1. registra y aprueba el pago;
2. genera el PDF;
3. guarda la factura en el buzón y en Facturas;
4. intenta enviarla al correo configurado.

Eliminar un mensaje enviado desde el panel lo quita del historial y del buzón interno. Un correo que ya llegó al proveedor no puede retirarse de la bandeja del destinatario.
