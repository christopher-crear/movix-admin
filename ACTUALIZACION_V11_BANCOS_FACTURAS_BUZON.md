# MOVIX V11 · Bancos, facturas y buzón

## 1. Actualizar Supabase

Si tu base ya tiene el módulo de mensualidades, ejecuta en **Supabase → SQL
Editor** únicamente:

```text
sql/payment_banks_inbox_invoices.sql
```

Si preparas una base nueva, basta ejecutar la versión actual de:

```text
sql/supabase_panel.sql
```

El script no borra datos. Crea:

- `payment_bank_accounts`: Banco de Loja, Banco Pichincha, Coopego y JEP.
- `driver_invoices`: facturas internas PDF vinculadas al pago y transportista.
- `driver_inbox_messages`: facturas, reuniones y avisos privados.
- Relaciones, índices, validaciones y políticas RLS.

Los bancos se instalan **ocultos**. Entra como administrador en **Bancos y
cuentas**, edita cada banco, registra titular/número/tipo, sube logo o QR si lo
deseas y pulsa **Publicar**.

## 2. Actualizar Django

En PowerShell, dentro del entorno virtual:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

La migración `panel.0005` registra en Django los modelos que apuntan a las
tablas de Supabase; no intenta volver a crear esas tablas.

## 3. Configurar el correo

Para Gmail activa la verificación en dos pasos y crea una **contraseña de
aplicación**. En `.env` local o en **Render → Environment** agrega:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=eraschristopher0@gmail.com
EMAIL_HOST_PASSWORD=CONTRASENA_DE_APLICACION
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=MOVIX <eraschristopher0@gmail.com>
```

No uses ni publiques la contraseña normal de Gmail. Si SMTP no está
configurado, la factura seguirá llegando al buzón interno y el administrador
verá el motivo por el cual no salió el correo.

## 4. Flujo funcional

1. El transportista abre **Mensualidad**, pulsa el logo de un banco y consulta
   los datos y QR configurados.
2. Sube un comprobante JPG, PNG, WEBP o PDF.
3. El administrador filtra la tabla por mes, estado, banco o texto y revisa el
   pago.
4. Después de aprobarlo pulsa **Generar y enviar factura**.
5. MOVIX genera el PDF, lo guarda de forma privada en Supabase, lo adjunta al
   correo y crea un mensaje en **Buzón**.
6. Desde **Mensajes transportistas**, el administrador también puede enviar
   reuniones, avisos de pago, estado de cuenta o mensajes generales.

La cédula puede subirse o reemplazarse desde **Mi perfil** del transportista.
Al actualizar un documento sensible se solicita una nueva verificación.
