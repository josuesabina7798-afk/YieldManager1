"""Base de datos local y reglas principales de Yield Manager."""

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from seguridad import (
    crear_hash_codigo,
    crear_hash_password,
    verificar_password,
    proteger_dato,
    revelar_dato,
)


# Windows guarda los datos de la aplicación en la carpeta local del usuario.
CARPETA_APP = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
CARPETA_APP = CARPETA_APP / "YieldManager"
ARCHIVO_BD = CARPETA_APP / "yield_manager.sqlite3"
ARCHIVO_SESION = CARPETA_APP / "sesion.bin"
ROLES = ("Administrador", "Almacenista", "Vendedor")


def fecha_hoy():
    """Devuelve la fecha de hoy en un formato que SQLite puede ordenar."""
    return date.today().isoformat()


def dias_para_caducar(fecha_caducidad):
    """Calcula cuántos días faltan para que venza un lote."""
    fecha = date.fromisoformat(fecha_caducidad)
    return (fecha - date.today()).days


def estado_caducidad(fecha_caducidad):
    """Asigna un estado de color según los días que le quedan al lote."""
    dias = dias_para_caducar(fecha_caducidad)
    if dias < 0:
        return "Vencido"
    if dias <= 3:
        return "Prioridad"
    if dias <= 7:
        return "Próximo"
    return "Seguro"


def validar_fecha(fecha_caducidad):
    """Comprueba el formato de la fecha y que no esté en el pasado."""
    try:
        fecha = date.fromisoformat(fecha_caducidad)
    except ValueError as error:
        raise ValueError("Escribe la fecha como AAAA-MM-DD.") from error

    if fecha < date.today():
        raise ValueError("La fecha no puede estar en el pasado.")


class BaseDatos:
    """Guarda cuentas, inventario y movimientos en un archivo SQLite local."""

    def __init__(self):
        CARPETA_APP.mkdir(parents=True, exist_ok=True)
        self.conexion = sqlite3.connect(ARCHIVO_BD, timeout=10)
        self.conexion.row_factory = sqlite3.Row
        self.conexion.execute("PRAGMA foreign_keys = ON")
        self._crear_tablas()
        self._actualizar_tablas_antiguas()
        self._limpiar_ejemplos_antiguos()

    def cerrar(self):
        """Cierra la conexión al salir de la aplicación."""
        self.conexion.close()

    def _crear_tablas(self):
        """Crea las tablas que la aplicación necesita si aún no existen."""
        self.conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                giro TEXT NOT NULL CHECK(giro IN ('Fábrica', 'Reventa')),
                minimum REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS lots (
                id INTEGER PRIMARY KEY,
                code TEXT NOT NULL,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                received TEXT NOT NULL,
                expiry TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity >= 0),
                location TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'Entrada',
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, code)
            );

            CREATE INDEX IF NOT EXISTS idx_lots_peps_initial
            ON lots(received, expiry, id);

            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY,
                at TEXT NOT NULL,
                kind TEXT NOT NULL,
                product TEXT NOT NULL,
                lot TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                user_email TEXT NOT NULL DEFAULT '',
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transformations (
                id INTEGER PRIMARY KEY,
                at TEXT NOT NULL,
                input_product TEXT NOT NULL,
                input_qty REAL NOT NULL,
                output_product TEXT NOT NULL,
                output_qty REAL NOT NULL,
                technical_waste REAL NOT NULL,
                yield REAL NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Almacenista',
                verified INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS email_codes (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                salt TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.conexion.commit()

    def _actualizar_tablas_antiguas(self):
        """Actualiza tablas viejas y separa los datos por cuenta."""
        columnas = {
            fila["name"]
            for fila in self.conexion.execute("PRAGMA table_info(movements)")
        }
        if "user_email" not in columnas:
            self.conexion.execute(
                "ALTER TABLE movements ADD COLUMN user_email TEXT NOT NULL DEFAULT ''"
            )
            self.conexion.commit()
        self._migrar_inventarios_por_cuenta()

    def _cuenta_para_datos_anteriores(self):
        """Elige al primer administrador para conservar el inventario anterior."""
        fila = self.conexion.execute(
            """
            SELECT id FROM users
            WHERE role = 'Administrador' AND active = 1
            ORDER BY id LIMIT 1
            """
        ).fetchone()
        if not fila:
            fila = self.conexion.execute(
                "SELECT id FROM users ORDER BY id LIMIT 1"
            ).fetchone()
        return fila["id"] if fila else None

    def _respaldar_base_antes_de_separar(self):
        """Crea una copia local antes de cambiar la estructura SQLite."""
        respaldo = CARPETA_APP / "yield_manager_antes_de_separar_cuentas.sqlite3"
        if respaldo.exists():
            return
        copia = sqlite3.connect(respaldo)
        self.conexion.backup(copia)
        copia.close()

    def _migrar_inventarios_por_cuenta(self):
        """Asigna los registros viejos y prepara las tablas por propietario."""
        tablas = ("products", "lots", "movements", "transformations")
        columnas = {
            tabla: {
                fila["name"]
                for fila in self.conexion.execute(f"PRAGMA table_info({tabla})")
            }
            for tabla in tablas
        }
        necesita_migracion = any(
            "user_id" not in nombres for nombres in columnas.values()
        )
        if not necesita_migracion:
            with self.conexion:
                self._crear_indices_por_cuenta()
            return

        self._respaldar_base_antes_de_separar()
        propietario = self._cuenta_para_datos_anteriores()
        reconstruir_catalogo = (
            "user_id" not in columnas["products"]
            or "user_id" not in columnas["lots"]
        )

        with self.conexion:
            if reconstruir_catalogo:
                self.conexion.execute("ALTER TABLE lots RENAME TO lots_legacy")
                self.conexion.execute(
                    "ALTER TABLE products RENAME TO products_legacy"
                )
                self.conexion.execute(
                    """
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        giro TEXT NOT NULL CHECK(giro IN ('Fábrica', 'Reventa')),
                        minimum REAL NOT NULL DEFAULT 0,
                        unit TEXT NOT NULL DEFAULT 'kg',
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        UNIQUE(user_id, name)
                    )
                    """
                )
                self.conexion.execute(
                    """
                    CREATE TABLE lots (
                        id INTEGER PRIMARY KEY,
                        code TEXT NOT NULL,
                        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                        received TEXT NOT NULL,
                        expiry TEXT NOT NULL,
                        quantity REAL NOT NULL CHECK(quantity >= 0),
                        location TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT 'Entrada',
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        UNIQUE(user_id, code)
                    )
                    """
                )

                if "user_id" in columnas["products"]:
                    propietario_producto = "COALESCE(user_id, ?)"
                else:
                    propietario_producto = "?"
                self.conexion.execute(
                    f"""
                    INSERT INTO products
                    (id, name, category, giro, minimum, unit, user_id)
                    SELECT id, name, category, giro, minimum, unit,
                           {propietario_producto}
                    FROM products_legacy
                    """,
                    (propietario,),
                )

                producto_tiene_cuenta = "user_id" in columnas["products"]
                lote_tiene_cuenta = "user_id" in columnas["lots"]
                if lote_tiene_cuenta and producto_tiene_cuenta:
                    propietario_lote = "COALESCE(l.user_id, p.user_id, ?)"
                elif lote_tiene_cuenta:
                    propietario_lote = "COALESCE(l.user_id, ?)"
                elif producto_tiene_cuenta:
                    propietario_lote = "COALESCE(p.user_id, ?)"
                else:
                    propietario_lote = "?"
                self.conexion.execute(
                    f"""
                    INSERT INTO lots
                    (id, code, product_id, received, expiry, quantity,
                     location, source, user_id)
                    SELECT l.id, l.code, l.product_id, l.received, l.expiry,
                           l.quantity, l.location, l.source,
                           {propietario_lote}
                    FROM lots_legacy AS l
                    LEFT JOIN products_legacy AS p ON p.id = l.product_id
                    """,
                    (propietario,),
                )
                self.conexion.execute("DROP TABLE lots_legacy")
                self.conexion.execute("DROP TABLE products_legacy")

            for tabla in ("movements", "transformations"):
                if "user_id" not in columnas[tabla]:
                    self.conexion.execute(
                        f"ALTER TABLE {tabla} ADD COLUMN user_id "
                        "INTEGER REFERENCES users(id) ON DELETE CASCADE"
                    )
                if propietario is not None:
                    self.conexion.execute(
                        f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL",
                        (propietario,),
                    )

            if propietario is not None:
                for tabla in ("products", "lots"):
                    self.conexion.execute(
                        f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL",
                        (propietario,),
                    )
            self._crear_indices_por_cuenta()

    def _crear_indices_por_cuenta(self):
        """Acelera la búsqueda dentro de la cuenta que inició sesión."""
        self.conexion.execute("DROP INDEX IF EXISTS idx_lots_peps_initial")
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_lots_peps "
            "ON lots(user_id, received, expiry, id)"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_user "
            "ON products(user_id, name)"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_movements_user "
            "ON movements(user_id, id)"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_transformations_user "
            "ON transformations(user_id, id)"
        )

    def _limpiar_ejemplos_antiguos(self):
        """Quita la base de muestra anterior solo si no tiene datos reales."""
        productos_demo = {
            "Pechuga de pollo", "Costilla de cerdo", "Arrachera marinada",
            "Chorizo premium", "Jamón de pierna"
        }
        lotes_demo = {
            "L-2609-0041", "L-2609-0038", "L-2609-0035",
            "L-2609-0043", "L-2609-0032", "L-2609-0044"
        }
        marca = self.conexion.execute(
            """
            SELECT COUNT(*) AS total FROM movements
            WHERE kind = 'Inicio' AND product = 'Sistema'
              AND detail = 'Datos de demostración'
            """
        ).fetchone()["total"]
        movimientos = self.conexion.execute(
            "SELECT COUNT(*) AS total FROM movements"
        ).fetchone()["total"]
        nombres = {
            fila["name"] for fila in self.conexion.execute("SELECT name FROM products")
        }
        codigos = {
            fila["code"] for fila in self.conexion.execute("SELECT code FROM lots")
        }
        transformaciones = self.conexion.execute(
            "SELECT COUNT(*) AS total FROM transformations"
        ).fetchone()["total"]

        es_solo_demo = (
            marca == 1
            and movimientos == 1
            and nombres == productos_demo
            and codigos == lotes_demo
            and transformaciones == 0
            and self.cantidad_cuentas() == 0
        )
        if not es_solo_demo:
            return

        # Se crea una copia local antes de quitar únicamente los datos de ejemplo.
        copia = CARPETA_APP / "yield_manager_respaldo_ejemplos.sqlite3"
        if not copia.exists():
            conexion_copia = sqlite3.connect(copia)
            self.conexion.backup(conexion_copia)
            conexion_copia.close()

        with self.conexion:
            self.conexion.execute("DELETE FROM lots")
            self.conexion.execute(
                "DELETE FROM movements WHERE detail = 'Datos de demostración'"
            )
            self.conexion.execute("DELETE FROM products")

    def cantidad_cuentas(self):
        """Cuenta las cuentas creadas para elegir el primer administrador."""
        fila = self.conexion.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        return fila["total"]

    def _asignar_datos_sin_cuenta(self, user_id):
        """Entrega datos antiguos sin propietario a la primera cuenta."""
        for tabla in ("products", "lots", "movements", "transformations"):
            self.conexion.execute(
                f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL",
                (user_id,),
            )

    def crear_cuenta(self, nombre, correo, password):
        """Registra una cuenta pendiente de verificar por correo."""
        correo = correo.strip().lower()
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Escribe tu nombre.")
        if len(password) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")

        salt, password_hash = crear_hash_password(password)
        rol = "Administrador" if self.cantidad_cuentas() == 0 else "Almacenista"
        creada = datetime.now().isoformat(timespec="seconds")

        try:
            with self.conexion:
                fila = self.conexion.execute(
                    "SELECT id, verified FROM users WHERE email = ?", (correo,)
                ).fetchone()

                if fila and fila["verified"]:
                    raise ValueError("Ya existe una cuenta verificada con ese correo.")

                if fila:
                    self.conexion.execute(
                        """
                        UPDATE users SET name = ?, salt = ?, password_hash = ?
                        WHERE id = ?
                        """,
                        (nombre, salt, password_hash, fila["id"]),
                    )
                    self._asignar_datos_sin_cuenta(fila["id"])
                    return fila["id"]

                cursor = self.conexion.execute(
                    """
                    INSERT INTO users
                    (email, name, salt, password_hash, role, verified, active, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, 1, ?)
                    """,
                    (correo, nombre, salt, password_hash, rol, creada),
                )
                user_id = cursor.lastrowid
                if self.cantidad_cuentas() == 1:
                    self._asignar_datos_sin_cuenta(user_id)
                return user_id
        except sqlite3.IntegrityError as error:
            raise ValueError("No se pudo crear la cuenta. Revisa el correo.") from error

    def buscar_cuenta(self, correo):
        """Busca una cuenta por correo sin distinguir mayúsculas."""
        return self.conexion.execute(
            "SELECT * FROM users WHERE email = ?", (correo.strip().lower(),)
        ).fetchone()

    def autenticar(self, correo, password):
        """Comprueba la contraseña, la verificación y el estado de la cuenta."""
        cuenta = self.buscar_cuenta(correo)
        if not cuenta or not verificar_password(
            password, cuenta["salt"], cuenta["password_hash"]
        ):
            raise ValueError("El correo o la contraseña no son correctos.")
        if not cuenta["verified"]:
            raise ValueError("Primero verifica tu correo con el código recibido.")
        if not cuenta["active"]:
            raise ValueError("La cuenta está desactivada. Consulta al administrador.")
        return cuenta

    def emitir_codigo(self, correo, codigo):
        """Guarda un código de seis dígitos con vencimiento de diez minutos."""
        cuenta = self.buscar_cuenta(correo)
        if not cuenta:
            raise ValueError("No se encontró esa cuenta.")
        if cuenta["verified"]:
            raise ValueError("La cuenta ya está verificada.")

        ahora = time.time()
        reciente = self.conexion.execute(
            """
            SELECT created_at FROM email_codes
            WHERE user_id = ? AND purpose = 'registro' AND used = 0
            ORDER BY id DESC LIMIT 1
            """,
            (cuenta["id"],),
        ).fetchone()
        if reciente and ahora - reciente["created_at"] < 60:
            raise ValueError("Espera un minuto antes de pedir otro código.")

        sal = secrets.token_bytes(16)
        codigo_hash = crear_hash_codigo(codigo, sal)
        with self.conexion:
            self.conexion.execute(
                """
                UPDATE email_codes SET used = 1
                WHERE user_id = ? AND purpose = 'registro' AND used = 0
                """,
                (cuenta["id"],),
            )
            self.conexion.execute(
                """
                INSERT INTO email_codes
                (user_id, purpose, salt, code_hash, expires_at, created_at)
                VALUES (?, 'registro', ?, ?, ?, ?)
                """,
                (
                    cuenta["id"],
                    sal.hex(),
                    codigo_hash,
                    ahora + 600,
                    ahora,
                ),
            )
        return cuenta["name"]

    def comprobar_codigo(self, correo, codigo):
        """Valida el código, limita intentos y confirma el registro."""
        cuenta = self.buscar_cuenta(correo)
        if not cuenta:
            raise ValueError("No se encontró esa cuenta.")

        reto = self.conexion.execute(
            """
            SELECT * FROM email_codes
            WHERE user_id = ? AND purpose = 'registro' AND used = 0
            ORDER BY id DESC LIMIT 1
            """,
            (cuenta["id"],),
        ).fetchone()

        if not reto:
            raise ValueError("Solicita un código nuevo por correo.")
        if reto["expires_at"] < time.time():
            self.conexion.execute(
                "UPDATE email_codes SET used = 1 WHERE id = ?", (reto["id"],)
            )
            self.conexion.commit()
            raise ValueError("El código venció. Solicita uno nuevo.")
        if reto["attempts"] >= 5:
            raise ValueError("Se agotaron los intentos. Solicita otro código.")

        hash_escrito = crear_hash_codigo(codigo.strip(), bytes.fromhex(reto["salt"]))
        if not secrets.compare_digest(hash_escrito, reto["code_hash"]):
            self.conexion.execute(
                "UPDATE email_codes SET attempts = attempts + 1 WHERE id = ?",
                (reto["id"],),
            )
            self.conexion.commit()
            raise ValueError("El código no es correcto.")

        with self.conexion:
            self.conexion.execute(
                "UPDATE email_codes SET used = 1 WHERE id = ?", (reto["id"],)
            )
            self.conexion.execute(
                "UPDATE users SET verified = 1 WHERE id = ?", (cuenta["id"],)
            )
        return cuenta

    def crear_sesion(self, user_id):
        """Crea una sesión de treinta días y devuelve su clave temporal."""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        vence = time.time() + 30 * 24 * 60 * 60
        with self.conexion:
            self.conexion.execute(
                "DELETE FROM sessions WHERE user_id = ?", (user_id,)
            )
            self.conexion.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, vence),
            )
        return token, token_hash

    def cuenta_de_sesion(self, token):
        """Recupera la cuenta si la sesión local aún está vigente."""
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        fila = self.conexion.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, time.time()),
        ).fetchone()
        if fila and fila["verified"] and fila["active"]:
            return fila
        self.conexion.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
        )
        self.conexion.commit()
        return None

    def cerrar_sesion(self, token):
        """Invalida la sesión actual cuando la persona cierra sesión."""
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.conexion.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
        )
        self.conexion.commit()

    def guardar_correo(self, configuracion):
        """Guarda SMTP y cifra la contraseña con Windows DPAPI."""
        anterior = self.obtener_correo()
        clave = configuracion.get("clave", "")
        if not clave and anterior:
            clave = anterior.get("clave", "")

        clave_cifrada = (
            base64.b64encode(proteger_dato(clave)).decode("ascii")
            if clave else ""
        )
        guardado = {
            "servidor": configuracion["servidor"].strip(),
            "puerto": int(configuracion["puerto"]),
            "usuario": configuracion.get("usuario", "").strip(),
            "remitente": configuracion["remitente"].strip(),
            "seguridad": configuracion["seguridad"],
            "probado": bool(configuracion.get("probado", False)),
            "clave_cifrada": clave_cifrada,
        }
        with self.conexion:
            self.conexion.execute(
                """
                INSERT INTO app_settings(name, value) VALUES ('smtp', ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (json.dumps(guardado),),
            )

    def obtener_correo(self):
        """Lee la configuración de correo y descifra la clave guardada."""
        fila = self.conexion.execute(
            "SELECT value FROM app_settings WHERE name = 'smtp'"
        ).fetchone()
        if not fila:
            return None

        configuracion = json.loads(fila["value"])
        cifrada = configuracion.pop("clave_cifrada")
        configuracion["clave"] = (
            revelar_dato(base64.b64decode(cifrada)) if cifrada else ""
        )
        return configuracion

    def crear_producto(
        self, user_id, nombre, categoria, giro, minimo, unidad, usuario
    ):
        """Agrega un producto al catálogo y anota el cambio."""
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Escribe el nombre del producto.")
        minimo = float(minimo)
        if minimo < 0:
            raise ValueError("El stock mínimo no puede ser negativo.")

        with self.conexion:
            self.conexion.execute(
                """
                INSERT INTO products
                (name, category, giro, minimum, unit, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (nombre, categoria, giro, minimo, unidad, user_id),
            )
            self._registrar_movimiento(
                user_id, "Catálogo", nombre, "", 0, "Producto agregado", usuario
            )

    def productos(self, user_id):
        """Devuelve el catálogo de la cuenta que inició sesión."""
        return self.conexion.execute(
            "SELECT * FROM products WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()

    def eliminar_producto(self, user_id, product_id, usuario):
        """Elimina un producto propio y sus lotes, y guarda el movimiento."""
        with self.conexion:
            producto = self.conexion.execute(
                "SELECT name FROM products WHERE id = ? AND user_id = ?",
                (product_id, user_id),
            ).fetchone()
            if not producto:
                raise ValueError("No se encontró ese producto en tu inventario.")

            # Guardamos el total antes del borrado para dejar constancia.
            lotes = self.conexion.execute(
                """
                SELECT COUNT(*) AS total, COALESCE(SUM(quantity), 0) AS cantidad
                FROM lots WHERE product_id = ? AND user_id = ?
                """,
                (product_id, user_id),
            ).fetchone()
            self.conexion.execute(
                "DELETE FROM products WHERE id = ? AND user_id = ?",
                (product_id, user_id),
            )
            self._registrar_movimiento(
                user_id, "Catálogo", producto["name"], "", lotes["cantidad"],
                f"Producto eliminado; {lotes['total']} lotes retirados",
                usuario,
            )

    def lotes(self, user_id, buscar="", giro=""):
        """Busca lotes propios y los ordena por fecha de ingreso PEPS."""
        consulta = """
            SELECT lots.*, products.name AS product, products.category,
                   products.giro, products.minimum, products.unit
            FROM lots
            JOIN products ON products.id = lots.product_id
            WHERE lots.user_id = ? AND products.user_id = ?
              AND lots.quantity > 0
        """
        valores = [user_id, user_id]
        if buscar.strip():
            consulta += " AND (products.name LIKE ? OR lots.code LIKE ?)"
            patron = f"%{buscar.strip()}%"
            valores.extend((patron, patron))
        if giro:
            consulta += " AND products.giro = ?"
            valores.append(giro)
        consulta += " ORDER BY lots.received, lots.expiry, lots.id"

        filas = self.conexion.execute(consulta, valores).fetchall()
        resultado = []
        for fila in filas:
            elemento = dict(fila)
            elemento["days_left"] = dias_para_caducar(elemento["expiry"])
            elemento["state"] = estado_caducidad(elemento["expiry"])
            resultado.append(elemento)
        return resultado

    def registrar_entrada(
        self, user_id, product_id, caducidad, cantidad, ubicacion, usuario
    ):
        """Crea un lote nuevo y registra su entrada en la bitácora."""
        validar_fecha(caducidad)
        cantidad = float(cantidad)
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")

        producto = self.conexion.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (product_id, user_id),
        ).fetchone()
        if not producto:
            raise ValueError("Selecciona un producto del catálogo.")

        codigo = (
            "L-"
            + datetime.now().strftime("%y%m%d-%H%M%S")
            + "-"
            + secrets.token_hex(2).upper()
        )
        with self.conexion:
            self.conexion.execute(
                """
                INSERT INTO lots
                (code, product_id, received, expiry, quantity, location,
                 source, user_id)
                VALUES (?, ?, ?, ?, ?, ?, 'Entrada', ?)
                """,
                (
                    codigo,
                    product_id,
                    fecha_hoy(),
                    caducidad,
                    cantidad,
                    ubicacion.strip(),
                    user_id,
                ),
            )
            self._registrar_movimiento(
                user_id, "Entrada", producto["name"], codigo, cantidad,
                f"Ingreso de {cantidad:g} {producto['unit']}", usuario
            )

    def descontar_lote(
        self, user_id, lot_id, cantidad, tipo, detalle, usuario
    ):
        """Resta una salida o merma si la cantidad está disponible."""
        cantidad = float(cantidad)
        lote = self.conexion.execute(
            """
            SELECT lots.*, products.name AS product
            FROM lots JOIN products ON products.id = lots.product_id
            WHERE lots.id = ? AND lots.user_id = ?
              AND products.user_id = ?
            """,
            (lot_id, user_id, user_id),
        ).fetchone()
        if not lote:
            raise ValueError("No se encontró el lote.")
        if cantidad <= 0 or cantidad > lote["quantity"]:
            raise ValueError(
                f"Cantidad inválida. Disponible: {lote['quantity']:g} kg."
            )
        if tipo == "Despacho" and date.fromisoformat(lote["expiry"]) < date.today():
            raise ValueError("El lote está vencido. Regístralo como merma.")

        with self.conexion:
            self.conexion.execute(
                "UPDATE lots SET quantity = quantity - ? "
                "WHERE id = ? AND user_id = ?",
                (cantidad, lot_id, user_id),
            )
            self._registrar_movimiento(
                user_id, tipo, lote["product"], lote["code"],
                cantidad, detalle, usuario
            )

    def registrar_transformacion(
        self, user_id, lot_id, cantidad_entrada, producto_salida_id,
        cantidad_salida, caducidad, usuario
    ):
        """Convierte materia prima y guarda rendimiento y merma técnica."""
        validar_fecha(caducidad)
        entrada = float(cantidad_entrada)
        salida = float(cantidad_salida)
        lote = self.conexion.execute(
            """
            SELECT lots.*, products.name AS product, products.giro
            FROM lots JOIN products ON products.id = lots.product_id
            WHERE lots.id = ? AND lots.user_id = ?
              AND products.user_id = ?
            """,
            (lot_id, user_id, user_id),
        ).fetchone()
        producto = self.conexion.execute(
            "SELECT * FROM products WHERE id = ? AND user_id = ?",
            (producto_salida_id, user_id),
        ).fetchone()

        if not lote or not producto:
            raise ValueError("Selecciona un lote y producto válidos.")
        if lote["giro"] != "Fábrica" or producto["giro"] != "Fábrica":
            raise ValueError("La transformación solo usa productos de Fábrica.")
        if lote["quantity"] <= 0 or entrada <= 0 or entrada > lote["quantity"]:
            raise ValueError("El peso de entrada supera lo disponible.")
        if salida <= 0 or salida > entrada:
            raise ValueError("La salida debe ser mayor que cero y no superar la entrada.")
        if date.fromisoformat(lote["expiry"]) < date.today():
            raise ValueError("No se puede transformar un lote vencido.")

        merma_tecnica = entrada - salida
        rendimiento = salida / entrada * 100
        codigo = (
            "T-"
            + datetime.now().strftime("%y%m%d-%H%M%S")
            + "-"
            + secrets.token_hex(2).upper()
        )

        with self.conexion:
            self.conexion.execute(
                "UPDATE lots SET quantity = quantity - ? "
                "WHERE id = ? AND user_id = ?",
                (entrada, lot_id, user_id),
            )
            self.conexion.execute(
                """
                INSERT INTO lots
                (code, product_id, received, expiry, quantity, location,
                 source, user_id)
                VALUES (?, ?, ?, ?, ?, ?, 'Transformación', ?)
                """,
                (
                    codigo, producto_salida_id, fecha_hoy(), caducidad,
                    salida, lote["location"], user_id
                ),
            )
            self.conexion.execute(
                """
                INSERT INTO transformations
                (at, input_product, input_qty, output_product, output_qty,
                 technical_waste, yield, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    lote["product"], entrada, producto["name"], salida,
                    merma_tecnica, rendimiento, user_id
                ),
            )
            detalle = (
                f"{entrada:g} kg → {salida:g} kg de {producto['name']}; "
                f"rendimiento {rendimiento:.1f}%; merma {merma_tecnica:g} kg"
            )
            self._registrar_movimiento(
                user_id, "Transformación", lote["product"], lote["code"],
                entrada, detalle, usuario
            )

    def _registrar_movimiento(
        self, user_id, tipo, producto, lote, cantidad, detalle, usuario
    ):
        """Agrega una fila a la bitácora de auditoría."""
        self.conexion.execute(
            """
            INSERT INTO movements
            (at, kind, product, lot, quantity, detail, user_email, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                tipo, producto, lote, cantidad, detalle, usuario, user_id
            ),
        )

    def movimientos(self, user_id, limite=500):
        """Devuelve movimientos recientes de la cuenta activa."""
        return self.conexion.execute(
            """
            SELECT * FROM movements WHERE user_id = ? ORDER BY id DESC LIMIT ?
            """,
            (user_id, limite),
        ).fetchall()

    def transformaciones(self, user_id):
        """Devuelve transformaciones de la cuenta activa."""
        return self.conexion.execute(
            "SELECT * FROM transformations WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()

    def reporte_productos(self, user_id):
        """Calcula existencias propias para cada producto."""
        productos = self.productos(user_id)
        lotes = self.lotes(user_id)
        resultado = []
        for producto in productos:
            lotes_producto = [
                lote for lote in lotes if lote["product"] == producto["name"]
            ]
            cantidad = sum(lote["quantity"] for lote in lotes_producto)
            resultado.append(
                {
                    "name": producto["name"],
                    "giro": producto["giro"],
                    "quantity": cantidad,
                    "lots": len(lotes_producto),
                    "minimum": producto["minimum"],
                    "state": "Bajo mínimo"
                    if cantidad < producto["minimum"]
                    else "En nivel",
                }
            )
        return resultado

    def total_merma(self, user_id):
        """Suma mermas de la cuenta activa."""
        fila = self.conexion.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS total FROM movements "
            "WHERE kind = 'Merma' AND user_id = ?",
            (user_id,),
        ).fetchone()
        return fila["total"]

    def usuarios(self):
        """Devuelve las cuentas para la pantalla del administrador."""
        return self.conexion.execute(
            "SELECT id, email, name, role, verified, active FROM users ORDER BY name"
        ).fetchall()

    def cambiar_usuario(self, user_id, role, active):
        """Actualiza el rol o activa y desactiva una cuenta."""
        if role not in ROLES:
            raise ValueError("Selecciona un rol válido.")
        if role != "Administrador" or not active:
            administradores = self.conexion.execute(
                """
                SELECT COUNT(*) AS total FROM users
                WHERE role = 'Administrador' AND active = 1 AND id != ?
                """,
                (user_id,),
            ).fetchone()["total"]
            if administradores == 0:
                raise ValueError("Debe quedar al menos un administrador activo.")
        with self.conexion:
            self.conexion.execute(
                "UPDATE users SET role = ?, active = ? WHERE id = ?",
                (role, int(active), user_id),
            )
            if not active:
                self.conexion.execute(
                    "DELETE FROM sessions WHERE user_id = ?", (user_id,)
                )

    def eliminar_cuenta(self, user_id):
        """Elimina una cuenta y los registros que le pertenecen."""
        cuenta = self.conexion.execute(
            "SELECT email, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not cuenta:
            raise ValueError("No se encontró la cuenta que quieres eliminar.")

        otros_usuarios = self.conexion.execute(
            "SELECT COUNT(*) AS total FROM users WHERE id != ?", (user_id,)
        ).fetchone()["total"]
        otros_administradores = self.conexion.execute(
            """
            SELECT COUNT(*) AS total FROM users
            WHERE role = 'Administrador' AND active = 1 AND id != ?
            """,
            (user_id,),
        ).fetchone()["total"]
        if (
            cuenta["role"] == "Administrador"
            and cuenta["active"]
            and otros_usuarios > 0
            and otros_administradores == 0
        ):
            raise ValueError(
                "No puedes eliminar al último administrador. "
                "Asigna otro administrador antes."
            )

        with self.conexion:
            self.conexion.execute(
                "DELETE FROM users WHERE id = ?", (user_id,)
            )
