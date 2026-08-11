# Actualización V5 · Portal privado del transportista

## Resultado

Se añadieron vistas privadas para transportistas dentro del mismo panel web de
MOVIX. Administradores y transportistas comparten el encabezado, el menú
lateral, los componentes y el acceso `/login/`; el rol solo determina las URL y
opciones que puede abrir cada sesión. Se consultan las mismas tablas de
Supabase utilizadas por la aplicación móvil, sin registros de demostración ni
copias de las carreras.

## Rutas nuevas

| Ruta | Función |
|---|---|
| `/login/` | Acceso unificado por rol |
| `/auth/callback/` | Retorno de Google/Supabase OAuth |
| `/transportista/` | Estadísticas y ganancias |
| `/transportista/carreras/` | Carreras asignadas y filtros |
| `/transportista/carreras/<uuid>/` | Detalle de una carrera propia |
| `/transportista/comentarios/` | Calificaciones y comentarios |
| `/transportista/perfil/` | Perfil, vehículo, documentos y contraseña |

## Tablas consultadas

- `auth.users`: identidad validada por Supabase Auth.
- `public.profiles`: rol y datos del transportista.
- `public.rides`: carreras cuyo `driver_id` es el UUID autenticado.
- `public.driver_reviews`: comentarios cuyo `driver_id` es el UUID autenticado.

## Variables nuevas

```env
SUPABASE_ANON_KEY="sb_publishable_TU_CLAVE_PUBLICA"
```

La `SUPABASE_SERVICE_ROLE_KEY` sigue siendo exclusivamente de backend. No debe
copiarse al navegador ni a la aplicación móvil.

## Configuración de Google

En Supabase, activa Google y registra estas URL de retorno:

```text
http://127.0.0.1:8000/auth/callback/
http://localhost:8000/auth/callback/
https://TU-SERVICIO.onrender.com/auth/callback/
```

En Google Cloud, la URI autorizada del proveedor es:

```text
https://PROJECT_REF.supabase.co/auth/v1/callback
```

## Protección aplicada

- El rol se toma de `profiles.role`, no de un campo enviado por el formulario.
- Una coincidencia entre `profiles.email` y el correo de un usuario Django
  `is_staff` no concede acceso administrativo. Esto evita que una cuenta de la
  app sea promovida por reutilizar el mismo Gmail.
- Solo `transportista`, `conductor` o `driver` abre el portal.
- La cuenta debe estar activa.
- Las rutas administrativas siguen exigiendo un usuario Django `is_staff`.
- El menú administrativo no se renderiza en una sesión de transportista.
- El menú del transportista solo enlaza Resumen, Mis carreras, Comentarios y Mi perfil.
- Cada detalle de carrera se filtra por UUID de carrera y UUID del conductor.
- El cambio de contraseña exige el token de la sesión Supabase autenticada.

## Base de datos

Esta actualización no requiere una migración ni SQL nuevo. Utiliza las columnas
existentes de `profiles`, `rides` y `driver_reviews`.

## Verificación

Se ejecutaron `python manage.py check` y 36 pruebas automatizadas. Incluyen login
Supabase, colisión entre correos Django/Supabase, acceso con Google, lectura de
estadísticas reales, uso del layout administrativo y bloqueo de carreras ajenas.
