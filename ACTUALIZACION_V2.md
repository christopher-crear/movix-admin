# Actualización MOVIX Admin v2

## Pasos obligatorios

1. Conserva tu archivo `.env` actual fuera de la carpeta antes de reemplazar el proyecto.
2. En Supabase abre **SQL Editor** y ejecuta completo `sql/supabase_panel.sql`.
   El script es idempotente: conserva los datos y puede ejecutarse nuevamente.
3. Copia tu `.env` dentro de la carpeta nueva. El ZIP no incluye credenciales.
4. Activa el entorno e instala/verifica dependencias:

   ```powershell
   .\venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```

## Cambios incluidos

- Ventana emergente única para imágenes y PDF, con descarga del original.
- Entradas pequeñas para nombres, correo, teléfono, cédula, placa y vehículo.
- Sincronización de `verified`, `profile_verified` y `verification_status`.
- Sincronización de `avatar_url` y `profile_photo_url`.
- Creación/verificación automática de buckets antes de cargar archivos.
- Guardado seguro: un fallo de base de datos ya no elimina el documento anterior.
- Mensajes claros para errores de clave, bucket, tamaño o conexión de Storage.
- Fotos de perfil en tablas, dashboard, detalles, edición y verificaciones.
- Búsqueda automática desde dos letras en usuarios, transportistas y documentos.
- Buscador superior limitado a los módulos del menú.
- Menos consultas repetidas y caché breve para reducir la latencia con Supabase.

## Variables necesarias para archivos

```env
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY="sb_secret_TU_CLAVE_SOLO_BACKEND"
SUPABASE_PUBLIC_BUCKET=movix-public
SUPABASE_PRIVATE_BUCKET=movix-documents
MAX_UPLOAD_MB=10
```

La clave debe ser una clave secreta del backend; no uses la clave pública o `anon`.
