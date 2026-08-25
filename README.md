# MOVIX Admin

Panel administrativo y portal privado de transportistas desarrollado con Django, Supabase PostgreSQL, Supabase Auth, Supabase Storage, Firebase Cloud Messaging opcional y Render.

El sistema utiliza las tablas existentes de la app móvil (`profiles`, `rides`, `driver_reviews` y `notifications`). Los modelos correspondientes tienen `managed = False`, por lo que Django no intenta recrearlas. El archivo `sql/supabase_panel.sql` incorpora únicamente los campos y tablas que faltaban para el panel.

## Funciones incluidas

- Página pública promocional de MOVIX en `/`, optimizada para escritorio y móvil.
- Demostración interactiva en `/demo/` con inicio, precios, selección de vehículo,
  carga, ubicación, pago, oferta y credencial. Todos sus perfiles, placas, rutas,
  precios e historiales son ficticios y nunca consultan ni modifican Supabase.
- Acceso social simulado para presentaciones con Google, Facebook o invitado, sin solicitar contraseñas.
- Animaciones suaves en tarjetas, teléfono flotante y secciones al hacer scroll.
- Información enfocada en transporte de carga liviana en Loja, Ecuador.
- Formulario público protegido con CSRF, campo trampa y límite básico por IP.
- Módulo **Solicitudes** para buscar, leer, responder por correo, cerrar y dar seguimiento a contactos.
- Secciones de descarga, vehículos, testimonios, métodos de pago, preguntas frecuentes y redes de contacto.
- Inicio de sesión unificado y enrutamiento seguro por rol.
- Pantalla de acceso MOVIX responsive con ilustración propia, logo oficial de Google, enlace a términos y recuperación de contraseña.
- Registro público de transportistas en `/registro-transportista/`, conectado con Supabase Auth, `profiles` y Storage.
- Registro guiado con foto tipo carnet, foto del vehículo, cédula, licencia, matrícula y seguro obligatorios; el perfil queda pendiente de revisión.
- Recuperación de contraseña por correo con enlace firmado de 30 minutos y formulario MOVIX para confirmar la nueva clave.
- Administradores mediante cuenta Django con `is_staff=True`.
- Transportistas mediante correo/contraseña de Supabase Auth o Google.
- Portal privado del transportista con ganancias por día, semana, mes y año, detalle por carrera y exportación CSV.
- Encomiendas multipunto con varias recogidas y entregas ordenadas, contacto por parada y tiempo en horas/minutos.
- Rangos automáticos `MOVIX Inicial`, `MOVIX Pro` y `Estrella MOVIX` para clientes y transportistas.
- Alerta visible para transportistas y administradores cuando un cliente tiene menos de 3 estrellas.
- Gestión de flotas por compañía: el dueño y cada chofer son perfiles completos de transportista con acceso propio a la app; el administrador únicamente los agrupa y los vehículos se obtienen de cada perfil.
- Permiso de operación cargable como fotografía o PDF, disponible en verificación documental.
- Listado paginado de carreras asignadas, filtros y detalle completo de cada servicio.
- Comentarios y calificaciones reales de `driver_reviews` con distribución por estrellas.
- Perfil del transportista con vehículo, documentos, edición y cambio de contraseña de Supabase.
- Selector controlado de vehículo: Camioneta, Camión pequeño o Camión mediano.
- Estado y visualización segura de todos los documentos cargados por el transportista.
- Mensualidades con Banco de Loja, Banco Pichincha, Banco Coopego o Cooperativa JEP; admite transferencia, depósito y comprobantes JPG/PNG/WEBP/PDF.
- Directorio bancario administrable con logos, titular, cuenta, instrucciones y código QR opcional; solo las cuentas activas se muestran al transportista.
- Revisión administrativa de pagos, registro de pagos físicos, aprobación, rechazo y notificación.
- Factura PDF automática para pagos aprobados, guardada en Supabase Storage y entregada al correo y al buzón privado del transportista.
- Módulo privado **Mis facturas** con búsqueda, filtro anual, vista previa y descarga individual de cada PDF.
- Buzón paginado con filtros para facturas, reuniones, pagos, estado de cuenta y avisos generales.
- Bloqueo o habilitación manual por falta de pago mediante `profiles.is_active`, con motivo visible para la app móvil y notificación interna/FCM.
- Foto real del cliente en el detalle de cada carrera cuando existe en Supabase.
- Aislamiento de datos: cada conductor solo consulta carreras y reseñas asociadas a su UUID.
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

Abre el proyecto de Supabase y entra en **SQL Editor**. Para una instalación
nueva ejecuta, en este orden:

```text
sql/supabase_panel.sql
sql/020_movix_routes_ranks_fleet.sql
sql/021_movix_admin_fleet_payments.sql
sql/022_movix_profile_fleets_and_permits.sql
```

El script puede ejecutarse más de una vez. No elimina información existente.
También sincroniza los registros antiguos que ya tenían `verified` o
`profile_verified=true`, por lo que conservarán correctamente su estado aprobado.

Si ya habías ejecutado una versión anterior de `supabase_panel.sql`, instala
las ampliaciones ejecutando, en este orden:

```text
sql/monthly_payments.sql
sql/payment_banks_inbox_invoices.sql
sql/020_movix_routes_ranks_fleet.sql
sql/021_movix_admin_fleet_payments.sql
sql/022_movix_profile_fleets_and_permits.sql
```

El segundo archivo crea las tablas `payment_bank_accounts`, `driver_invoices`
y `driver_inbox_messages`, sus relaciones, índices y políticas RLS. También
registra los cuatro bancos como ocultos. En el panel entra en **Bancos y
cuentas**, completa los datos reales y activa únicamente los que usarás.

`020_movix_routes_ranks_fleet.sql` añade `ride_stops`, `fleet_vehicles`,
`fleet_drivers`, la vista `profile_ranks`, las relaciones de flota en `rides`,
índices y políticas RLS. También convierte cada carrera antigua en una ruta de
dos paradas sin borrar ni modificar sus direcciones originales.

`021_movix_admin_fleet_payments.sql` incorpora la base de pagos mensuales,
validaciones de formato, control administrativo y notificaciones que se eliminan
al abrirlas. La estructura auxiliar de flota de esta etapa se migra al modelo
definitivo mediante el archivo siguiente.

`022_movix_profile_fleets_and_permits.sql` aplica el modelo definitivo de
flotas: agrega `is_fleet_owner` y `fleet_owner_id` a `profiles`, protege la
agrupación para que solo la cambie el administrador y agrega el documento
`permit_photo_url`. Cada chofer conserva una cuenta real de Supabase Auth, su
vehículo y todas las funciones normales de transportista. La mensualidad se
registra por cada perfil de transportista y, por tanto, por su vehículo.

Los rangos se calculan así: **Estrella MOVIX** desde 100 carreras y 4,7;
**MOVIX Pro** desde 40 carreras y 4,3; los demás perfiles usan **MOVIX Inicial**.

La app móvil debe comprobar `profiles.is_active` después del inicio de sesión y
antes de permitir solicitudes/aceptaciones. Cuando el administrador bloquea una
cuenta, el panel establece `is_active=false`, guarda `blocked_reason` y crea una
fila en `notifications` para que la app muestre el motivo.

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
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API Keys → Publishable/anon key |
| `SECRET_KEY` | Genera una clave de Django |

### Configurar Brevo para facturas, avisos y respuestas

MOVIX utiliza el mismo proveedor para enviar facturas, reuniones, avisos y las
respuestas del módulo **Solicitudes**. En Render Free se usa Brevo por HTTPS,
porque los puertos SMTP están bloqueados.

1. Crea una API Key en Brevo y verifica el remitente.
2. Configura estas variables en Render → Environment:

```env
EMAIL_PROVIDER=brevo
BREVO_API_KEY=TU_API_KEY_PRIVADA
BREVO_SENDER_EMAIL=eraschristopher0@gmail.com
BREVO_SENDER_NAME=MOVIX
```

3. Ejecuta **Manual Deploy → Deploy latest commit** en Render.

Puedes comprobar el envío desde la consola del proyecto, reemplazando el correo
de destino:

```powershell
python manage.py shell -c "from panel.services import send_movix_email; print(send_movix_email('TU_CORREO@gmail.com', 'Prueba MOVIX', 'El correo de MOVIX funciona correctamente.'))"
```

El resultado correcto es `(True, '')`. Si Brevo falla, los mensajes y respuestas
siguen guardados y MOVIX muestra el motivo devuelto por la API. Nunca publiques
`.env` ni `BREVO_API_KEY` en GitHub.

Para desarrollo local también se puede usar SMTP con `EMAIL_PROVIDER=smtp` y
las variables `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD` y `EMAIL_USE_TLS`.

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

La migración `panel/0002_contactrequest` crea automáticamente
`public.contact_requests`, donde se almacenan las consultas de la landing. No
debes crearla manualmente si `migrate` terminó correctamente. El archivo
`sql/contact_requests.sql` queda incluido como alternativa para instalaciones
en las que el esquema se gestione exclusivamente desde Supabase SQL Editor.

Si ejecutaste primero ese SQL y luego aparece `relation "contact_requests"
already exists`, conserva la tabla y registra la migración sin volverla a crear:

```powershell
python manage.py migrate panel 0002 --fake
python manage.py migrate
```

La cuenta creada con `createsuperuser` permite entrar al panel administrativo. Los
transportistas ingresan en la misma pantalla con el correo y contraseña que ya
usan en Supabase Auth. Django comprueba el UUID autenticado en `public.profiles`
y abre automáticamente el portal del transportista. Las cuentas de clientes no
reciben acceso a este portal web.

Ejecuta:

```powershell
python manage.py runserver
```

Abre `http://127.0.0.1:8000/` para ver la página pública y
`http://127.0.0.1:8000/login/` para entrar. El rol autenticado decide si se abre
el panel administrativo o `/transportista/`.

Desde la landing y el login se puede abrir
`http://127.0.0.1:8000/registro-transportista/`. El servidor crea primero la
identidad en Supabase Auth, guarda los datos en `public.profiles`, carga las
fotos/documentos en los buckets correspondientes y deja la verificación en
estado `pending`. No se requiere una tabla adicional para este flujo.

La opción **¿Olvidaste tu contraseña?** envía un enlace al correo registrado.
El enlace dura 30 minutos y solo puede utilizarse una vez. Para cuentas de
transportistas, Django cambia la clave mediante Supabase Auth con
`SUPABASE_SERVICE_ROLE_KEY`; para administradores actualiza la cuenta Django.

Los datos públicos de contacto se pueden cambiar en `.env` mediante
`MOVIX_SUPPORT_EMAIL`, `MOVIX_WHATSAPP_NUMBER`, `MOVIX_WHATSAPP_DISPLAY` y
`MOVIX_FACEBOOK_URL`. La página pública enlaza el **Portal transportista**, pero
nunca expone permisos administrativos. Entrar a `/login/` no concede acceso:
cada ruta vuelve a validar la sesión y el rol.

## 4. Iniciar sesión con Google mediante Supabase

1. En Google Cloud crea credenciales **OAuth 2.0 / Aplicación web**.
2. En **URI de redireccionamiento autorizados** agrega:

```text
https://PROJECT_REF.supabase.co/auth/v1/callback
```

3. En Supabase abre **Authentication → Providers → Google**, actívalo y pega el
   Client ID y Client Secret de Google.
4. En **Authentication → URL Configuration → Redirect URLs** agrega:

```text
http://127.0.0.1:8000/auth/callback/
http://localhost:8000/auth/callback/
https://TU-SERVICIO.onrender.com/auth/callback/
```

5. Comprueba que el usuario de Google tenga una fila en `public.profiles` con el
   mismo UUID de `auth.users.id` y un rol aceptado: `transportista`, `conductor`
   o `driver`.

El navegador recibe el token OAuth en el fragmento de la URL y lo entrega por
POST con CSRF a Django. El servidor vuelve a validarlo contra Supabase antes de
crear la sesión del portal.

## 5. Archivos y Supabase Storage

El SQL crea dos buckets:

- `movix-public`: banners, foto de perfil, vehículo y fotos administrativas públicas.
- `movix-documents`: cédulas, licencias, matrículas y seguros privados.

Los documentos privados se guardan como `storage://bucket/ruta`. Django genera enlaces firmados temporales para visualizarlos o descargarlos. Render no se usa para guardar archivos permanentes.

Si un bucket todavía no existe, el backend intenta crearlo automáticamente con
la clave secreta. Aun así, ejecuta `sql/supabase_panel.sql` para instalar columnas,
índices, sincronización de fotos y estados de verificación.

El panel admite JPG, PNG, WEBP y PDF, hasta 10 MB por defecto.
La foto o PDF de la cédula puede renovarse desde **Mi perfil** del transportista;
al cambiar un documento sensible el perfil vuelve a estado pendiente para una
nueva revisión administrativa.

## 6. Bancos, facturas y buzón en la app móvil

La app puede leer las cuentas visibles, las facturas del usuario autenticado y
su propio buzón gracias a las políticas RLS:

```javascript
const { data: banks } = await supabase
  .from('payment_bank_accounts')
  .select('*')
  .eq('is_active', true)
  .order('sort_order')

const { data: inbox } = await supabase
  .from('driver_inbox_messages')
  .select('*, driver_invoices(*)')
  .order('created_at', { ascending: false })
```

Para marcar un mensaje como leído, actualiza únicamente `is_read` y `read_at`.
La política impide consultar mensajes o facturas de otro transportista.

## 7. Notificaciones push

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

## 8. Publicidad en la app móvil

La aplicación puede consultar los banners visibles así:

```javascript
const { data } = await supabase
  .from('advertisements')
  .select('*')
  .eq('is_active', true)
  .order('created_at', { ascending: false })
```

La política RLS incluida solamente permite leer anuncios activos y dentro de sus fechas.

## 9. Publicar en Render

1. Sube esta carpeta a un repositorio privado de GitHub.
2. En Render selecciona **New → Blueprint**.
3. Conecta el repositorio; Render detectará `render.yaml`.
4. Completa las variables marcadas como secretas.
   Incluye `SUPABASE_ANON_KEY`; la `SERVICE_ROLE_KEY` no reemplaza esta
   configuración de acceso de Supabase Auth.
5. En `ALLOWED_HOSTS` coloca `tu-servicio.onrender.com`.
6. En `CSRF_TRUSTED_ORIGINS` coloca `https://tu-servicio.onrender.com`.
7. Cuando termine el despliegue, abre **Shell** y ejecuta:

```bash
python manage.py createsuperuser
```

Render ejecuta automáticamente instalación, archivos estáticos, migraciones y comprobaciones de producción con `build.sh`.

Después del primer despliegue añade la URL exacta de Render terminada en
`/auth/callback/` a las Redirect URLs de Supabase. Si cambias variables, ejecuta
**Manual Deploy → Clear build cache & deploy**.

## 9. Correspondencia con la base existente

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
| Solicitudes de la página pública | `contact_requests` |

## Seguridad

- Nunca coloques `SUPABASE_SERVICE_ROLE_KEY` en la app móvil o en JavaScript del navegador.
- La clave anon/publishable identifica el proyecto, pero no reemplaza las
  políticas RLS ni concede privilegios administrativos.
- Usa un repositorio privado y mantén `.env` fuera de Git.
- El panel administrativo exige `is_staff=True`; las vistas de transportista
  exigen una sesión Supabase válida enlazada a un perfil transportista activo.
- El correo por sí solo no concede permisos: Google y Supabase respetan
  `profiles.role`; una cuenta administrativa por OAuth requiere además un rol
  administrativo explícito y un usuario Django `is_staff` habilitado.
- Ambos roles usan la misma interfaz web. Las URL y el menú se construyen según
  el rol, sin exponer enlaces administrativos al transportista.
- El detalle de carrera filtra simultáneamente por `ride.id` y `driver_id`.
- Los archivos se validan por tamaño y tipo.
- Los documentos privados usan enlaces con caducidad.
- Las eliminaciones muestran confirmación y se registran en auditoría.
- Antes de producción, crea una copia de seguridad de Supabase y prueba primero con datos de prueba controlados.
# Actualización V17

Para habilitar el bloqueo real compatible con la app y el descarte seguro de notificaciones, ejecuta en Supabase SQL Editor:

`sql/010_account_blocks_and_notification_links.sql`

Consulta `ACTUALIZACION_V17_BLOQUEO_GOOGLE_NOTIFICACIONES.md` para integrar el gesto `Dismissible` de Flutter y probar el registro con Google y el pago físico con factura automática.
