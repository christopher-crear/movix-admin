# MOVIX Admin

Panel administrativo de producción desarrollado con Django, Supabase PostgreSQL, Supabase Storage, Firebase Cloud Messaging opcional y Render.

El sistema utiliza las tablas existentes de la app móvil (`profiles`, `rides`, `driver_reviews` y `notifications`). Los modelos correspondientes tienen `managed = False`, por lo que Django no intenta recrearlas. El archivo `sql/supabase_panel.sql` incorpora únicamente los campos y tablas que faltaban para el panel.

## Funciones incluidas

- Inicio de sesión exclusivo para cuentas Django con `is_staff=True`.
- Dashboard con contadores y gráficos calculados desde la base real.
- Usuarios y transportistas separados según el campo `profiles.role`.
- Creación integrada con Supabase Auth y `public.profiles`.
- Visualización, edición, bloqueo, desbloqueo y eliminación.
- Eliminación coordinada con Supabase Auth.
- Búsqueda, filtros, paginación y exportación CSV.
- Carga segura de imágenes y PDF a Supabase Storage.
- Vista previa y descarga de documentos privados mediante enlaces firmados.
- Vista previa de imágenes y PDF dentro de una ventana emergente, sin abrir pestañas nuevas.
- Aprobación y rechazo de verificaciones con motivo y notificación al usuario.
- Banners publicitarios con carga, activación, desactivación y eliminación.
- Notificaciones internas masivas o individuales.
- Push mediante FCM cuando la app registra tokens en `device_tokens`.
- Historial de campañas y auditoría administrativa.
- Perfil administrativo, cambio de contraseña y eliminación protegida.
- Configuración general y modo oscuro.
- Menú lateral desplegable, versión móvil y confirmaciones de acciones peligrosas.
- Buscadores automáticos desde dos caracteres y buscador superior exclusivo para módulos.
- Fotos reales de perfil en listados, detalles, dashboard y verificaciones.
- Consultas agrupadas y caché breve para reducir la latencia de Supabase.
- Configuración preparada para Render.

## 1. Ejecutar el SQL requerido

Abre el proyecto de Supabase y entra en **SQL Editor**. Copia y ejecuta todo el archivo:

```text
sql/supabase_panel.sql
```

El script puede ejecutarse más de una vez. No elimina información existente.
También sincroniza los registros antiguos que ya tenían `verified` o
`profile_verified=true`, por lo que conservarán correctamente su estado aprobado.

## 2. Preparar el proyecto en Windows

Abre PowerShell en la carpeta del proyecto:

```powershell
py -3.14 -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copia las variables de ejemplo:

```powershell
Copy-Item .env.example .env
```

Edita `.env` y coloca tus valores. No publiques ese archivo ni compartas la clave `service_role`.

### Variables obligatorias

| Variable | Origen |
|---|---|
| `DATABASE_URL` | Supabase → Connect → Session pooler, puerto 5432 |
| `SUPABASE_URL` | Supabase → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → clave secreta del servidor |
| `SECRET_KEY` | Genera una clave de Django |

Genera `SECRET_KEY` con:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Si la contraseña PostgreSQL contiene caracteres como `@`, `#`, `%`, `:` o `/`, debe codificarse para una URL dentro de `DATABASE_URL`.

## 3. Crear las tablas administrativas de Django

```powershell
python manage.py migrate
python manage.py createsuperuser
```

La cuenta creada con `createsuperuser` es la que permite entrar al panel. Los clientes y transportistas no pueden iniciar sesión aquí.

Ejecuta:

```powershell
python manage.py runserver
```

Abre `http://127.0.0.1:8000/login/`.

## 4. Archivos y Supabase Storage

El SQL crea dos buckets:

- `movix-public`: banners, foto de perfil, vehículo y fotos administrativas públicas.
- `movix-documents`: cédulas, licencias, matrículas y seguros privados.

Los documentos privados se guardan como `storage://bucket/ruta`. Django genera enlaces firmados temporales para visualizarlos o descargarlos. Render no se usa para guardar archivos permanentes.

Si un bucket todavía no existe, el backend intenta crearlo automáticamente con
la clave secreta. Aun así, ejecuta `sql/supabase_panel.sql` para instalar columnas,
índices, sincronización de fotos y estados de verificación.

El panel admite JPG, PNG, WEBP y PDF, hasta 10 MB por defecto.

## 5. Notificaciones push

Las notificaciones internas funcionan inmediatamente y se guardan en `public.notifications`.

Para push real:

1. Crea una cuenta de servicio en Firebase Console.
2. Coloca su JSON completo en `FIREBASE_CREDENTIALS_JSON` de Render. Localmente también puedes colocar la ruta absoluta del archivo.
3. La app móvil debe insertar o actualizar su token FCM en `public.device_tokens` después del login.

Ejemplo conceptual desde Supabase JS en la app:

```javascript
await supabase.from('device_tokens').upsert({
  user_id: user.id,
  token: fcmToken,
  platform: 'android',
  is_active: true,
}, { onConflict: 'token' })
```

Si Firebase aún no está configurado, el panel guarda las notificaciones internas y muestra `0 push`; no se pierde el mensaje.

## 6. Publicidad en la app móvil

La aplicación puede consultar los banners visibles así:

```javascript
const { data } = await supabase
  .from('advertisements')
  .select('*')
  .eq('is_active', true)
  .order('created_at', { ascending: false })
```

La política RLS incluida solamente permite leer anuncios activos y dentro de sus fechas.

## 7. Publicar en Render

1. Sube esta carpeta a un repositorio privado de GitHub.
2. En Render selecciona **New → Blueprint**.
3. Conecta el repositorio; Render detectará `render.yaml`.
4. Completa las variables marcadas como secretas.
5. En `ALLOWED_HOSTS` coloca `tu-servicio.onrender.com`.
6. En `CSRF_TRUSTED_ORIGINS` coloca `https://tu-servicio.onrender.com`.
7. Cuando termine el despliegue, abre **Shell** y ejecuta:

```bash
python manage.py createsuperuser
```

Render ejecuta automáticamente instalación, archivos estáticos, migraciones y comprobaciones de producción con `build.sh`.

## 8. Correspondencia con la base existente

| Módulo | Tabla principal |
|---|---|
| Usuarios y transportistas | `profiles` |
| Carreras y estadísticas | `rides` |
| Calificaciones | `driver_reviews` |
| Notificaciones en la app | `notifications` |
| Campañas administrativas | `admin_notification_campaigns` |
| Tokens push | `device_tokens` |
| Publicidad | `advertisements` |
| Auditoría | `admin_audit_logs` |
| Configuración | `admin_settings` |

## Seguridad

- Nunca coloques `SUPABASE_SERVICE_ROLE_KEY` en la app móvil o en JavaScript del navegador.
- Usa un repositorio privado y mantén `.env` fuera de Git.
- El panel exige `is_staff=True` en todas las rutas.
- Los archivos se validan por tamaño y tipo.
- Los documentos privados usan enlaces con caducidad.
- Las eliminaciones muestran confirmación y se registran en auditoría.
- Antes de producción, crea una copia de seguridad de Supabase y prueba primero con datos de prueba controlados.
