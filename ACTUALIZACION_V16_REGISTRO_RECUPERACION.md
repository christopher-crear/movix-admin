# MOVIX V16 — Registro, acceso y recuperación

## Funciones nuevas

- Login MOVIX rediseñado y adaptable a teléfono, tableta y escritorio.
- Ilustración propia de una ruta MOVIX con camión y entrega.
- Botón de Google con el identificador visual oficial; mantiene el flujo OAuth de Supabase.
- Registro público de transportistas en `/registro-transportista/`.
- Guía visible para foto tipo carnet, foto del vehículo y documentos legibles.
- Carga obligatoria de cédula, licencia, matrícula, seguro, perfil y vehículo.
- Aceptación obligatoria de términos de demostración antes de crear la cuenta.
- Recuperación de contraseña en `/recuperar-contrasena/` con enlace firmado,
  vencimiento de 30 minutos y uso único.

## No hace falta ejecutar SQL nuevo

El registro utiliza `auth.users`, `public.profiles`, `movix-public` y
`movix-documents`, que ya forman parte de MOVIX. Conserva ejecutado
`sql/supabase_panel.sql` de las versiones anteriores.

## Variables necesarias en Render

```env
SUPABASE_URL=https://TU_PROYECTO.supabase.co
SUPABASE_ANON_KEY=TU_CLAVE_PUBLICA
SUPABASE_SERVICE_ROLE_KEY=TU_CLAVE_SECRETA_SOLO_BACKEND
EMAIL_PROVIDER=brevo
BREVO_API_KEY=TU_API_KEY_PRIVADA
BREVO_SENDER_EMAIL=eraschristopher0@gmail.com
BREVO_SENDER_NAME=MOVIX
MOVIX_SUPPORT_EMAIL=eraschristopher0@gmail.com
```

En Brevo, `eraschristopher0@gmail.com` debe aparecer como remitente verificado.
La recuperación, la bienvenida, las facturas y los avisos usan ese mismo
remitente.

## Google en Supabase

En **Authentication → URL Configuration → Redirect URLs** conserva:

```text
http://127.0.0.1:8000/auth/callback/
http://localhost:8000/auth/callback/
https://TU-SERVICIO.onrender.com/auth/callback/
```

Y en las credenciales OAuth de Google agrega como URI autorizada la devolución
de Supabase:

```text
https://TU_PROYECTO.supabase.co/auth/v1/callback
```

## Prueba local

```powershell
python manage.py check
python manage.py test panel
python manage.py runserver
```

Abre `/registro-transportista/`, crea una cuenta con un correo nuevo y confirma
que los seis archivos quedan visibles en **Verificar documentos**. Luego prueba
`/recuperar-contrasena/` y revisa Spam o Promociones si el mensaje no aparece en
la bandeja principal.
