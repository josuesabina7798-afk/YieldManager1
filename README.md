# Yield Manager para Windows

Yield Manager es una aplicación de escritorio para registrar el inventario de Procesadora Don Juan. La información de productos, lotes, usuarios y movimientos se guarda en SQLite en esta computadora.

## Iniciar la aplicación

1. Abre **Iniciar Yield Manager.bat**.
2. En el primer uso, configura el correo de salida desde la pantalla de acceso.
3. Crea una cuenta. La primera cuenta verificada será Administrador.
4. Al confirmar el código, la app abre la cuenta automáticamente.
5. Entra a **⚙ Configuración** para cambiar el correo o eliminar tu cuenta.
6. En los siguientes ingresos, puedes marcar **Mantener sesión iniciada en este equipo** para abrir la app sin volver a escribir la contraseña.

La sesión recordada dura hasta 30 días o hasta que cierres sesión. Windows protege el archivo de sesión con DPAPI. La contraseña de la cuenta se guarda como hash con sal; el programa no guarda esa contraseña en texto.

Cada cuenta tiene su propio catálogo, inventario, movimientos, reportes y transformaciones. Los datos compartidos de versiones anteriores se asignan al primer administrador activo; las demás cuentas empiezan con un inventario separado. Antes de migrar se crea una copia local de la base de datos.

Al eliminar una cuenta también se eliminan sus productos, lotes, movimientos y transformaciones. Los datos de las otras cuentas no cambian. Si queda más de una cuenta, no se puede eliminar al último administrador activo.

## Configurar la verificación por correo

La app no se publica en internet. Para enviar códigos, necesita conexión a internet y una cuenta de correo que permita SMTP.

En **Configurar correo de verificación**, escribe los datos SMTP de tu proveedor:

- Servidor y puerto SMTP.
- Usuario SMTP y correo remitente.
- Tipo de conexión segura: STARTTLS o SSL.
- Contraseña o clave de aplicación del correo.

Usa una clave de aplicación cuando tu proveedor lo requiera. Pulsa **Probar envío**, confirma que llegue el mensaje a tu correo y después pulsa **Guardar correo**. El botón de configuración y el texto informativo desaparecen de la pantalla de acceso después de guardar una prueba correcta. Windows cifra localmente la contraseña SMTP. No escribas esa clave dentro del código.

Los códigos vencen a los 10 minutos, se pueden usar una sola vez y permiten cinco intentos. La app espera 60 segundos antes de permitir otro envío.

## Funciones

- Registro de productos de Fábrica o Reventa.
- Entrada de lotes con caducidad, cantidad y ubicación.
- Inventario con búsqueda y prioridad por caducidad.
- Despacho sugerido por PEPS y validación de existencias.
- Registro de mermas con su causa.
- Transformación de materia prima y cálculo de rendimiento.
- Reporte de existencias, exportación CSV y opción de impresión a PDF.
- Bitácora con la cuenta que registró cada movimiento.
- Cuentas con roles de Administrador, Almacenista y Vendedor.

La aplicación inicia sin productos ni lotes de ejemplo. Si la base antigua contiene solamente los registros predeterminados de demostración, la aplicación crea primero una copia local y los retira. Si detecta movimientos o datos adicionales, conserva la base antigua.

## Archivos de la aplicación

- yield_manager.pyw: pantallas y navegación.
- base_datos.py: SQLite, inventario, cuentas y reglas del negocio.
- seguridad.py: hashes de contraseña, protección local y envío SMTP.

Los tres archivos usan módulos incluidos con Python y Tkinter. La base se encuentra en %LOCALAPPDATA%\YieldManager\yield_manager.sqlite3.
