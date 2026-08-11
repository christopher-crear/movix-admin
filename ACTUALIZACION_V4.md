# MOVIX Admin V5 — previsualizaciones y Supabase Storage real

## Problemas encontrados

La versión recibida solo comprobaba si los campos como `identification_photo_url`
tenían texto. La plantilla mostraba un icono, no una miniatura real. Además, el
backend solo interpretaba `storage://bucket/ruta` y URLs HTTPS completas. Las
rutas guardadas por la app móvil como `carpeta/archivo.jpg`, URLs firmadas
caducadas o rutas relativas terminaban produciendo una imagen rota.

## Correcciones

- Miniaturas pequeñas y centradas para cédula, licencia, matrícula, seguro,
  perfil y vehículo.
- Franja **Ampliar documento** y modal con la imagen completa usando
  `object-fit: contain`.
- La portada administrativa usa una imagen real con `object-fit: cover` y
  rellena todo el recuadro.
- Se reconocen URLs públicas, privadas, firmadas, `storage://`, rutas relativas,
  `bucket/ruta` y rutas sin bucket.
- Una URL firmada almacenada en la base se renueva antes de mostrarla.
- Si falta el bucket en el campo, el panel busca una coincidencia real en
  `storage.objects`.
- Si el campo tiene texto pero el objeto no existe, se muestra un diagnóstico
  legible en vez del icono roto del navegador.

## Diagnóstico de la base de datos recibida

El JSON exportado de Supabase confirma que los archivos sí están almacenados.
El proyecto usa tres ubicaciones que deben resolverse de forma diferente:

- `movix-documents`: privado; contiene cédulas y documentos nuevos del panel.
- `profile-media`: público; contiene archivos históricos subidos por la app móvil.
- `movix-public`: público; contiene perfiles, vehículos y banners nuevos.

Por eso no se recrearon tablas ni se movieron objetos. El backend ahora consulta
el bucket real de cada coincidencia en `storage.objects` y revisa el atributo
`public` de `storage.buckets`. Los objetos privados se firman con la clave de
servicio y los públicos generan su URL pública sin firmas innecesarias.

## Diseño unificado de archivos

- Marco celeste y miniatura pequeña centrada con `object-fit: contain`.
- Nombre del archivo y botón **Descargar original**.
- Botón **Ampliar** que abre una única ventana emergente.
- Django actúa como proxy seguro: descarga el objeto con una URL pública o
  firmada recién generada y lo entrega desde el mismo dominio del panel. El
  navegador ya no depende directamente de enlaces privados temporales.
- Mensaje legible si Supabase no puede entregar el objeto; nunca se muestra el
  icono roto del navegador.
- Previsualización local antes de guardar en usuarios, transportistas,
  publicidad, foto administrativa y portada.
- Los PDF muestran la primera página en miniatura y se abren completos en el
  modal con los controles del visor del navegador. La ruta administrativa usa
  `SAMEORIGIN` para permitir el visor sin autorizar sitios externos.
- La portada sí usa `object-fit: cover` porque debe llenar su recuadro.

## SQL de diagnóstico reutilizable

Ejecuta `sql/diagnostico_supabase_movix.sql` en **Supabase > SQL Editor**. El
archivo es de solo lectura y genera un único JSON con tablas, columnas,
relaciones, índices, triggers, RLS, políticas, permisos, buckets, objetos y las
rutas de archivos guardadas en `profiles`.

Si `coincidencias_storage` aparece como `[]`, la aplicación móvil guardó una
ruta en `profiles`, pero el archivo no está en Supabase Storage o se guardó con
otro nombre. En ese caso hay que corregir también la carga en Flutter; el panel
web no puede reconstruir una imagen cuyos bytes nunca llegaron al bucket.

## Variables necesarias

Los documentos privados requieren en desarrollo y Render:

```env
SUPABASE_URL=https://TU_PROYECTO.supabase.co
SUPABASE_SERVICE_ROLE_KEY=CLAVE_SECRETA_REAL_DEL_BACKEND
SUPABASE_PUBLIC_BUCKET=movix-public
SUPABASE_PRIVATE_BUCKET=movix-documents
```

No uses la clave `anon` o `publishable` como `SUPABASE_SERVICE_ROLE_KEY`.

## Despliegue de los estilos corregidos en Render

En **Settings > Build & Deploy**, el comando de construcción debe ser
exactamente:

```bash
bash build.sh
```

No debe quedar solamente `pip install -r requirements.txt`, porque así Render
no recopila el CSS nuevo. `build.sh` ahora limpia y vuelve a crear
`staticfiles`; las reglas críticas de miniaturas también están versionadas e
incluidas en el HTML para impedir que una caché anterior vuelva a agrandar las
imágenes.

Después de subir esta versión usa **Manual Deploy > Clear build cache & deploy**
y, al terminar, recarga el navegador con `Ctrl + F5`.

No se añadieron tablas ni migraciones. Esta entrega fue validada con 31 pruebas
automatizadas de Django.

## Corrección V6: visor PDF y perfil administrativo

- El modal elimina la etiqueta de imagen antes de cargar un PDF y oculta con
  prioridad el elemento inactivo. Ya no aparece el espacio vacío ni el icono de
  imagen rota encima del visor PDF.
- La vista de Perfil ahora muestra portada completa, avatar superpuesto,
  información personal, actividad, contraseña y zona de peligro siguiendo la
  composición del diseño de referencia.
- El botón **Editar perfil** abre un modo de edición separado; **Cancelar
  edición** vuelve a la vista de lectura sin guardar cambios.
- **Cambiar portada** lleva directamente al modo de edición y la portada se
  mantiene con `object-fit: cover` para rellenar el recuadro.
- Los archivos CSS y JavaScript se versionaron como `20260810-60` para evitar
  que el navegador reutilice la versión defectuosa de su caché.

Esta corrección no requiere SQL ni nuevas migraciones y mantiene las 31 pruebas
automatizadas aprobadas.
