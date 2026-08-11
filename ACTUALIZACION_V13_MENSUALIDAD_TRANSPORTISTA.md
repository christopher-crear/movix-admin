# MOVIX V13 — Mensualidad del transportista

Esta actualización corrige la pantalla de pagos del transportista y los filtros del administrador.

## Cambios incluidos

- Las cuentas bancarias se muestran como tarjetas compactas sin desbordamientos.
- Al pulsar **Ver datos de pago** se abre una ventana emergente con titular, cuenta, tipo, cédula/RUC, instrucciones y QR.
- El botón **Usar esta cuenta** selecciona automáticamente el banco en el formulario.
- El selector de bancos utiliza únicamente las cuentas activas publicadas por el administrador.
- El selector de tipo de pago incluye transferencia bancaria, depósito bancario y pago físico.
- Transferencias y depósitos requieren comprobante; el pago físico puede registrarse sin archivo.
- Los controles de mes y banco del administrador tienen anchos compactos y separación adaptable.
- Se añadieron pruebas para opciones bancarias, modal y registro de pago físico.

## Base de datos

Esta versión no crea migraciones ni requiere ejecutar SQL adicional.

