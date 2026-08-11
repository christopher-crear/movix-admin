# MOVIX V12 — rediseño de mensualidades, bancos y mensajes

Esta versión reorganiza los tres módulos administrativos nuevos para que usen la misma identidad visual del resto del panel MOVIX.

## Pagos de transportistas

- Resumen compacto con estados e iconos diferenciados.
- Filtros agrupados en una sola tarjeta y buscador sin recortes.
- Pestañas de estado claras y desplazables en móvil.
- Tabla contenida, acciones ordenadas y paginación integrada.
- Distribución adaptable para escritorio, tableta y móvil.

## Bancos y cuentas

- Formulario con jerarquía, ayudas y campos legibles.
- Selector de archivos estilizado para logo y QR.
- Directorio de bancos en tarjetas consistentes.
- Estado visible/oculto, información bancaria y QR claramente separados.
- Mejor flujo para editar, publicar u ocultar una cuenta.

## Mensajes a transportistas

- Formulario de redacción compacto y explícito.
- Programación de reuniones y envío por correo mejor identificados.
- Historial dentro de una tarjeta con buscador y filtro de tipo.
- Estado vacío explicativo y paginación integrada.

## Verificación

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- 45 pruebas automatizadas: correctas.

No requiere SQL ni migraciones nuevas: esta actualización modifica presentación, distribución y ayudas de formularios sin alterar la estructura de Supabase.
