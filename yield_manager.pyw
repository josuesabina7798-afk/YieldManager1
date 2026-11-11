"""Interfaz de escritorio para Yield Manager."""

import csv
import html
import tkinter as tk
import webbrowser
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from base_datos import ARCHIVO_SESION, BaseDatos, ROLES
from seguridad import (
    correo_valido, crear_codigo, enviar_codigo, enviar_correo_prueba,
    proteger_dato, revelar_dato,
)

# Colores comunes de la interfaz.
VERDE = "#164b3b"
VERDE_OSCURO = "#123c32"
FONDO = "#f4f7f4"
TEXTO = "#1c2d26"
SUAVE = "#718078"
BORDE = "#dfe8e1"
ROJO = "#b43c35"
AMARILLO = "#a96e05"


class Aplicacion(tk.Tk):
    """Controla las pantallas y conecta la interfaz con la base local."""

    def __init__(self):
        super().__init__()
        self.title("Yield Manager · Procesadora Don Juan")
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.configure(bg=FONDO)
        self.base = BaseDatos()
        self.usuario = None
        self.token_sesion = None
        self.estilo = ttk.Style(self)
        self._configurar_estilo()
        self.contenedor = tk.Frame(self, bg=FONDO)
        self.contenedor.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.mostrar_inicio()
        self._restaurar_sesion()

    def _configurar_estilo(self):
        """Configura los controles de las tablas y los botones."""
        self.estilo.theme_use("clam")
        self.estilo.configure(
            "Treeview", rowheight=34, font=("Segoe UI", 10),
            background="white", fieldbackground="white", foreground=TEXTO
        )
        self.estilo.configure(
            "Treeview.Heading", font=("Segoe UI", 9, "bold"),
            background="#edf2ee", foreground=TEXTO, padding=(9, 9)
        )
        self.estilo.map(
            "Treeview", background=[("selected", "#dcebe1")],
            foreground=[("selected", TEXTO)]
        )
        self.estilo.configure(
            "TButton", font=("Segoe UI", 9, "bold"), padding=(11, 8)
        )
        self.estilo.configure(
            "Accent.TButton", font=("Segoe UI", 9, "bold"),
            padding=(13, 9), background=VERDE, foreground="white"
        )
        self.estilo.configure(
            "Danger.TButton", font=("Segoe UI", 9, "bold"),
            padding=(11, 8), background=ROJO, foreground="white"
        )
        self.estilo.map(
            "Accent.TButton", background=[("active", VERDE_OSCURO)],
            foreground=[("active", "white")]
        )
        self.estilo.map(
            "Danger.TButton", background=[("active", "#942f2a")],
            foreground=[("active", "white")]
        )
        self.estilo.configure("TCombobox", padding=5)

    def _limpiar(self):
        """Retira la pantalla actual antes de mostrar otra."""
        for elemento in self.contenedor.winfo_children():
            elemento.destroy()

    def mostrar_inicio(self, mensaje=""):
        """Abre la pantalla para iniciar sesión."""
        self._limpiar()
        PantallaInicio(self.contenedor, self, mensaje).pack(
            fill="both", expand=True
        )

    def mostrar_registro(self):
        """Abre la pantalla para crear una cuenta nueva."""
        self._limpiar()
        PantallaRegistro(self.contenedor, self).pack(fill="both", expand=True)

    def mostrar_codigo(self, correo, mensaje=""):
        """Abre la pantalla para comprobar el código del correo."""
        self._limpiar()
        PantallaCodigo(self.contenedor, self, correo, mensaje).pack(
            fill="both", expand=True
        )

    def mostrar_correo(self, volver_a="inicio", datos_vuelta=None):
        """Abre la configuración del servidor de correo."""
        self._limpiar()
        PantallaCorreo(self.contenedor, self, volver_a, datos_vuelta).pack(
            fill="both", expand=True
        )

    def correo_configurado(self):
        """Indica si el correo quedó probado y guardado correctamente."""
        try:
            configuracion = self.base.obtener_correo()
        except Exception:
            return False
        return bool(
            configuracion
            and configuracion.get("probado")
            and configuracion.get("servidor")
            and configuracion.get("remitente")
        )

    def pedir_codigo(self, correo):
        """Guarda un código temporal y lo manda al correo indicado."""
        configuracion = self.base.obtener_correo()
        if not configuracion:
            raise ValueError("Primero configura el correo de verificación.")
        codigo = crear_codigo()
        nombre = self.base.emitir_codigo(correo, codigo)
        enviar_codigo(configuracion, correo, codigo)
        return nombre

    def iniciar_sesion(self, cuenta, recordar):
        """Abre la app y guarda una sesión si se eligió recordarla."""
        self.usuario = cuenta
        self.token_sesion = None
        if recordar:
            token, _ = self.base.crear_sesion(cuenta["id"])
            try:
                ARCHIVO_SESION.write_bytes(proteger_dato(token))
                self.token_sesion = token
            except (OSError, RuntimeError) as error:
                self.base.cerrar_sesion(token)
                messagebox.showwarning(
                    "Sesión no guardada",
                    "Entraste, pero Windows no pudo recordar la sesión.\n\n"
                    f"{error}",
                    parent=self,
                )
        else:
            self._borrar_sesion_guardada()

        self._limpiar()
        VistaPrincipal(self.contenedor, self, cuenta).pack(
            fill="both", expand=True
        )

    def _restaurar_sesion(self):
        """Inicia automáticamente si existe una sesión local válida."""
        if not ARCHIVO_SESION.exists():
            return
        try:
            token = revelar_dato(ARCHIVO_SESION.read_bytes())
            cuenta = self.base.cuenta_de_sesion(token)
        except (OSError, RuntimeError, ValueError):
            self._borrar_sesion_guardada()
            return
        if cuenta:
            self.token_sesion = token
            self.usuario = cuenta
            self._limpiar()
            VistaPrincipal(self.contenedor, self, cuenta).pack(
                fill="both", expand=True
            )
        else:
            self._borrar_sesion_guardada()

    def _borrar_sesion_guardada(self):
        """Elimina la sesión recordada de esta computadora."""
        if self.token_sesion:
            self.base.cerrar_sesion(self.token_sesion)
        self.token_sesion = None
        try:
            ARCHIVO_SESION.unlink(missing_ok=True)
        except OSError:
            pass

    def cerrar_sesion(self):
        """Cierra la sesión y regresa al formulario de acceso."""
        self._borrar_sesion_guardada()
        self.usuario = None
        self.mostrar_inicio("La sesión se cerró correctamente.")

    def _cerrar(self):
        """Cierra la base de datos antes de cerrar la ventana."""
        self.base.cerrar()
        self.destroy()


def crear_tarjeta(padre, ancho=450):
    """Crea un panel blanco para agrupar un formulario."""
    tarjeta = tk.Frame(
        padre, bg="white", highlightbackground=BORDE,
        highlightthickness=1, padx=32, pady=28, width=ancho
    )
    return tarjeta


def etiqueta(padre, texto, grande=False, color=TEXTO):
    """Crea una etiqueta con el estilo común de la aplicación."""
    tamano = 20 if grande else 10
    peso = "bold" if grande else "normal"
    return tk.Label(
        padre, text=texto, font=("Segoe UI", tamano, peso),
        fg=color, bg="white", anchor="w", justify="left"
    )


def entrada(padre, variable=None, secreto=False):
    """Crea una caja de texto sencilla."""
    campo = tk.Entry(
        padre, textvariable=variable, show="●" if secreto else "",
        font=("Segoe UI", 10), relief="solid", bd=1,
        highlightthickness=1, highlightbackground=BORDE,
        highlightcolor=VERDE, insertbackground=TEXTO
    )
    campo.pack(fill="x", ipady=8, pady=(4, 12))
    return campo


def boton_enlace(padre, texto, comando):
    """Crea un botón de texto para cambiar de pantalla."""
    return tk.Button(
        padre, text=texto, command=comando,
        font=("Segoe UI", 9, "underline"), fg=VERDE, bg="white",
        activeforeground=VERDE_OSCURO, activebackground="white",
        relief="flat", cursor="hand2"
    )


def boton_principal(padre, texto, comando):
    """Crea el botón verde de acción principal."""
    return tk.Button(
        padre, text=texto, command=comando,
        font=("Segoe UI", 10, "bold"), fg="white", bg=VERDE,
        activebackground=VERDE_OSCURO, activeforeground="white",
        relief="flat", cursor="hand2", padx=14, pady=10
    )


class PantallaInicio(tk.Frame):
    """Permite iniciar sesión y recordar el acceso en este equipo."""

    def __init__(self, padre, app, mensaje=""):
        super().__init__(padre, bg=FONDO)
        self.app = app
        self.correo = tk.StringVar()
        self.password = tk.StringVar()
        self.recordar = tk.BooleanVar(value=False)
        envoltura = tk.Frame(self, bg=FONDO)
        envoltura.place(relx=0.5, rely=0.5, anchor="center")
        tarjeta = crear_tarjeta(envoltura)
        tarjeta.pack()

        etiqueta(tarjeta, "YIELD MANAGER", grande=True, color=VERDE).pack(fill="x")
        etiqueta(tarjeta, "Control de inventario cárnico").pack(
            fill="x", pady=(3, 20)
        )
        etiqueta(tarjeta, "Correo electrónico").pack(fill="x")
        entrada(tarjeta, self.correo)
        etiqueta(tarjeta, "Contraseña").pack(fill="x")
        campo = entrada(tarjeta, self.password, secreto=True)
        campo.bind("<Return>", lambda evento: self._entrar())
        tk.Checkbutton(
            tarjeta, text="Mantener sesión iniciada en este equipo",
            variable=self.recordar, bg="white", fg=TEXTO,
            activebackground="white", selectcolor="white",
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(0, 12))
        boton_principal(tarjeta, "Iniciar sesión", self._entrar).pack(fill="x")

        if mensaje:
            etiqueta(tarjeta, mensaje, color=VERDE).pack(
                fill="x", pady=(12, 0)
            )
        fila = tk.Frame(tarjeta, bg="white")
        fila.pack(fill="x", pady=(14, 0))
        boton_enlace(
            fila, "Crear una cuenta", app.mostrar_registro
        ).pack(side="left")
        if not app.correo_configurado():
            boton_enlace(
                tarjeta, "Configurar correo",
                lambda: app.mostrar_correo("inicio")
            ).pack(anchor="center", pady=(10, 0))

    def _entrar(self):
        """Comprueba las credenciales antes de mostrar el inventario."""
        try:
            cuenta = self.app.base.autenticar(
                self.correo.get(), self.password.get()
            )
        except ValueError as error:
            if "Primero verifica tu correo" in str(error):
                try:
                    self.app.pedir_codigo(self.correo.get().strip().lower())
                    mensaje = "Enviamos un nuevo código a tu correo."
                except Exception:
                    mensaje = "No se pudo enviar el código. Revisa el correo configurado."
                self.app.mostrar_codigo(
                    self.correo.get().strip().lower(), mensaje
                )
                return
            messagebox.showerror("No se pudo iniciar sesión", str(error))
            return
        self.app.iniciar_sesion(cuenta, self.recordar.get())


class PantallaRegistro(tk.Frame):
    """Registra una cuenta pendiente y envía un código de verificación."""

    def __init__(self, padre, app):
        super().__init__(padre, bg=FONDO)
        self.app = app
        self.nombre = tk.StringVar()
        self.correo = tk.StringVar()
        self.password = tk.StringVar()
        self.confirmacion = tk.StringVar()
        tarjeta = crear_tarjeta(self)
        tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        etiqueta(tarjeta, "Crear cuenta", grande=True).pack(fill="x")
        etiqueta(
            tarjeta,
            "Completa tus datos para recibir el código de verificación.",
            color=SUAVE
        ).pack(fill="x", pady=(5, 17))
        etiqueta(tarjeta, "Nombre").pack(fill="x")
        entrada(tarjeta, self.nombre)
        etiqueta(tarjeta, "Correo electrónico").pack(fill="x")
        entrada(tarjeta, self.correo)
        etiqueta(tarjeta, "Contraseña (mínimo 8 caracteres)").pack(fill="x")
        entrada(tarjeta, self.password, secreto=True)
        etiqueta(tarjeta, "Confirmar contraseña").pack(fill="x")
        campo = entrada(tarjeta, self.confirmacion, secreto=True)
        campo.bind("<Return>", lambda evento: self._crear())
        boton_principal(
            tarjeta, "Enviar código al correo", self._crear
        ).pack(fill="x", pady=(5, 4))
        boton_enlace(
            tarjeta, "Volver a iniciar sesión", app.mostrar_inicio
        ).pack(anchor="center", pady=(8, 0))

    def _crear(self):
        """Guarda los datos y cambia a la pantalla del código."""
        nombre = self.nombre.get().strip()
        correo = self.correo.get().strip().lower()
        password = self.password.get()
        if not correo_valido(correo):
            messagebox.showerror("Revisa el correo", "Escribe un correo válido.")
            return
        if password != self.confirmacion.get():
            messagebox.showerror(
                "Revisa la contraseña", "Las contraseñas no coinciden."
            )
            return
        try:
            self.app.base.crear_cuenta(nombre, correo, password)
        except Exception as error:
            messagebox.showerror("No se pudo crear la cuenta", str(error))
            return
        try:
            self.app.pedir_codigo(correo)
            mensaje = "Enviamos un código de seis dígitos a tu correo."
        except Exception:
            mensaje = (
                "La cuenta quedó pendiente. Revisa la configuración del correo "
                "e inténtalo de nuevo."
            )
        self.app.mostrar_codigo(correo, mensaje)


class PantallaCodigo(tk.Frame):
    """Comprueba el código de seis dígitos recibido por correo."""

    def __init__(self, padre, app, correo, mensaje=""):
        super().__init__(padre, bg=FONDO)
        self.app = app
        self.correo = correo
        self.codigo = tk.StringVar()
        tarjeta = crear_tarjeta(self, ancho=470)
        tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        etiqueta(tarjeta, "Verificar correo", grande=True).pack(fill="x")
        etiqueta(
            tarjeta, f"Escribe el código enviado a {correo}.", color=SUAVE
        ).pack(fill="x", pady=(5, 15))
        etiqueta(tarjeta, "Código de seis dígitos").pack(fill="x")
        campo = entrada(tarjeta, self.codigo)
        campo.bind("<Return>", lambda evento: self._confirmar())
        if mensaje:
            etiqueta(tarjeta, mensaje, color=VERDE).pack(
                fill="x", pady=(0, 9)
            )
        boton_principal(
            tarjeta, "Confirmar código", self._confirmar
        ).pack(fill="x")
        boton_enlace(
            tarjeta, "Solicitar otro código", self._reenviar
        ).pack(anchor="center", pady=(8, 0))
        boton_enlace(
            tarjeta, "Configurar correo",
            lambda: app.mostrar_correo("codigo", (correo, ""))
        ).pack(anchor="center", pady=(3, 0))
        boton_enlace(
            tarjeta, "Volver al inicio", app.mostrar_inicio
        ).pack(anchor="center", pady=(3, 0))

    def _confirmar(self):
        """Valida el código y abre la pantalla siguiente."""
        if len(self.codigo.get().strip()) != 6:
            messagebox.showerror("Código inválido", "Escribe los seis dígitos.")
            return
        try:
            cuenta = self.app.base.comprobar_codigo(
                self.correo, self.codigo.get()
            )
        except ValueError as error:
            messagebox.showerror("No se pudo verificar", str(error))
            return
        self.app.iniciar_sesion(cuenta, recordar=False)

    def _reenviar(self):
        """Solicita un código nuevo cuando ya pasó el tiempo de espera."""
        try:
            self.app.pedir_codigo(self.correo)
        except Exception:
            messagebox.showerror(
                "No se pudo enviar",
                "Revisa la configuración del correo e inténtalo de nuevo."
            )
            return
        messagebox.showinfo("Código enviado", "Revisa tu correo electrónico.")


class PantallaCorreo(tk.Frame):
    """Configura el servidor SMTP que envía los códigos de cuenta."""

    def __init__(self, padre, app, volver_a, datos_vuelta=None):
        super().__init__(padre, bg=FONDO)
        self.app = app
        self.volver_a = volver_a
        self.datos_vuelta = datos_vuelta
        self.variables = {
            "servidor": tk.StringVar(),
            "puerto": tk.StringVar(value="587"),
            "usuario": tk.StringVar(),
            "remitente": tk.StringVar(),
            "seguridad": tk.StringVar(value="STARTTLS"),
            "clave": tk.StringVar(),
        }
        self.clave_guardada = False
        self.prueba_correcta = False
        tarjeta = crear_tarjeta(self, ancho=560)
        tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        etiqueta(tarjeta, "Configurar correo", grande=True).pack(fill="x")
        etiqueta(
            tarjeta, "Completa los datos de tu cuenta de correo.", color=SUAVE
        ).pack(fill="x", pady=(5, 15))
        self._campo(tarjeta, "Servidor de correo", "servidor")
        self._campo(tarjeta, "Puerto", "puerto")
        self._campo(tarjeta, "Correo de la cuenta", "usuario")
        self._campo(tarjeta, "Correo remitente", "remitente")
        etiqueta(tarjeta, "Seguridad de conexión").pack(fill="x")
        ttk.Combobox(
            tarjeta, textvariable=self.variables["seguridad"],
            values=("STARTTLS", "SSL"), state="readonly"
        ).pack(fill="x", pady=(4, 12))
        self._campo(
            tarjeta, "Contraseña o clave de aplicación", "clave", True
        )
        fila = tk.Frame(tarjeta, bg="white")
        fila.pack(fill="x", pady=(6, 0))
        ttk.Button(
            fila, text="Probar envío", command=self._probar
        ).pack(side="left")
        self.boton_guardar = ttk.Button(
            fila, text="Guardar correo", command=self._guardar,
            state="disabled"
        )
        self.boton_guardar.pack(side="right")
        boton_enlace(
            tarjeta, "Volver", self._volver
        ).pack(anchor="center", pady=(10, 0))
        self._cargar_configuracion()
        for variable in self.variables.values():
            variable.trace_add("write", self._reiniciar_prueba)

    def _reiniciar_prueba(self, *_):
        """Exige otra prueba si se cambia algún dato SMTP."""
        self.prueba_correcta = False
        self.boton_guardar.configure(state="disabled")

    def _campo(self, padre, titulo, clave, secreto=False):
        """Agrega una caja de texto con su etiqueta."""
        etiqueta(padre, titulo).pack(fill="x")
        return entrada(
            padre, self.variables[clave], secreto=secreto
        )

    def _cargar_configuracion(self):
        """Rellena el formulario si ya existe un servidor guardado."""
        try:
            configuracion = self.app.base.obtener_correo()
        except Exception:
            messagebox.showwarning(
                "No se pudo abrir la configuración",
                "Inténtalo de nuevo. Si el problema continúa, pide ayuda al administrador."
            )
            return
        if not configuracion:
            return
        for clave in (
            "servidor", "puerto", "usuario", "remitente", "seguridad"
        ):
            self.variables[clave].set(str(configuracion.get(clave, "")))
        self.clave_guardada = bool(configuracion.get("clave"))
        self.variables["clave"].set("")

    def _leer_configuracion(self):
        """Comprueba los valores y prepara la conexión SMTP."""
        datos = {
            clave: variable.get().strip()
            for clave, variable in self.variables.items()
        }
        if not datos["servidor"] or not datos["remitente"]:
            raise ValueError("Escribe el servidor y el correo remitente.")
        if not correo_valido(datos["remitente"]):
            raise ValueError("El correo remitente no tiene un formato válido.")
        try:
            puerto = int(datos["puerto"])
        except ValueError as error:
            raise ValueError("El puerto debe ser un número.") from error
        if not 1 <= puerto <= 65535:
            raise ValueError("El puerto debe estar entre 1 y 65535.")
        if datos["usuario"] and not datos["clave"] and not self.clave_guardada:
            raise ValueError(
                "Escribe la contraseña o clave de aplicación del correo."
            )
        if not datos["usuario"]:
            datos["clave"] = ""
        datos["puerto"] = puerto
        return datos

    def _probar(self):
        """Envía un correo de prueba al remitente configurado."""
        self._reiniciar_prueba()
        try:
            configuracion = self._leer_configuracion()
            if not configuracion["clave"] and self.clave_guardada:
                anterior = self.app.base.obtener_correo()
                configuracion["clave"] = anterior["clave"]
            enviar_correo_prueba(configuracion)
        except Exception:
            messagebox.showerror(
                "No se pudo enviar el mensaje de prueba",
                "Revisa tu conexión a internet, los datos del servidor y la clave de aplicación."
            )
            return
        messagebox.showinfo(
            "Correo probado", "Se envió un mensaje de prueba al remitente."
        )
        self.prueba_correcta = True
        self.boton_guardar.configure(state="normal")

    def _guardar(self):
        """Guarda los datos y cifra la contraseña SMTP en Windows."""
        if not self.prueba_correcta:
            messagebox.showwarning(
                "Falta probar el correo",
                "Pulsa «Probar envío» y confirma que llegue el mensaje antes de guardar."
            )
            return
        try:
            configuracion = self._leer_configuracion()
            configuracion["probado"] = True
            self.app.base.guardar_correo(configuracion)
        except Exception:
            messagebox.showerror(
                "No se pudo guardar el correo",
                "Revisa los datos e inténtalo de nuevo."
            )
            return
        messagebox.showinfo(
            "Correo guardado",
            "Correo de verificación guardado."
        )
        self._volver()

    def _volver(self):
        """Vuelve al inicio de sesión o al panel de operación."""
        if self.volver_a == "codigo" and self.datos_vuelta:
            self.app.mostrar_codigo(*self.datos_vuelta)
            return
        if self.volver_a == "principal" and self.app.usuario:
            self.app._limpiar()
            VistaPrincipal(
                self.app.contenedor, self.app, self.app.usuario
            ).pack(fill="both", expand=True)
        else:
            self.app.mostrar_inicio()


class Formulario(tk.Toplevel):
    """Muestra campos breves para las operaciones del inventario."""

    def __init__(self, padre, titulo, campos, al_guardar):
        super().__init__(padre)
        self.title(titulo)
        self.configure(bg="white")
        self.resizable(False, False)
        self.transient(padre)
        self.grab_set()
        self.al_guardar = al_guardar
        self.variables = {}
        self.opciones = {}
        marco = tk.Frame(self, bg="white", padx=22, pady=18)
        marco.pack(fill="both", expand=True)
        etiqueta(marco, titulo, grande=True).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        for fila, campo in enumerate(campos, start=1):
            clave, nombre, tipo, opciones, inicial = campo
            tk.Label(
                marco, text=nombre, font=("Segoe UI", 9, "bold"),
                fg=TEXTO, bg="white"
            ).grid(row=fila, column=0, sticky="w", padx=(0, 15), pady=6)
            variable = tk.StringVar(value=inicial or "")
            self.variables[clave] = variable
            if tipo == "lista":
                textos = [opcion[0] for opcion in opciones]
                self.opciones[clave] = dict(opciones)
                caja = ttk.Combobox(
                    marco, textvariable=variable,
                    values=textos, state="readonly"
                )
                if not variable.get() and textos:
                    variable.set(textos[0])
            else:
                caja = ttk.Entry(marco, textvariable=variable, width=34)
            caja.grid(row=fila, column=1, sticky="ew", pady=5)

        botones = tk.Frame(marco, bg="white")
        botones.grid(
            row=len(campos) + 1, column=0, columnspan=2,
            sticky="e", pady=(15, 0)
        )
        ttk.Button(
            botones, text="Cancelar", command=self.destroy
        ).pack(side="left", padx=5)
        ttk.Button(
            botones, text="Guardar", command=self._guardar
        ).pack(side="left")
        self.bind("<Return>", lambda evento: self._guardar())
        self.update_idletasks()
        self.geometry(f"+{padre.winfo_rootx() + 140}+{padre.winfo_rooty() + 100}")

    def _guardar(self):
        """Entrega los datos limpios a la acción correspondiente."""
        datos = {}
        for clave, variable in self.variables.items():
            texto = variable.get().strip()
            datos[clave] = self.opciones.get(clave, {}).get(texto, texto)
        try:
            self.al_guardar(datos)
        except Exception as error:
            messagebox.showerror(
                "No se pudo guardar", str(error), parent=self
            )
            return
        self.destroy()


class VistaPrincipal(tk.Frame):
    """Organiza el trabajo según el rol de la cuenta activa."""

    def __init__(self, padre, app, usuario):
        super().__init__(padre, bg=FONDO)
        self.app = app
        self.base = app.base
        self.usuario = usuario
        self.pagina_actual = "Resumen"
        self.variables_filtro = {}
        self._crear_marco()
        self.mostrar_pagina("Resumen")

    def _paginas_permitidas(self):
        """Devuelve las pantallas disponibles para el rol actual."""
        paginas = ["Resumen", "Inventario"]
        if self.usuario["role"] in ("Administrador", "Almacenista"):
            paginas.append("Producción")
        if self.usuario["role"] == "Administrador":
            paginas.extend(["Reportes", "Actividad", "Usuarios"])
        return paginas

    def _crear_marco(self):
        """Dibuja la navegación y el área principal."""
        # La barra reúne las páginas y los movimientos más usados.
        barra = tk.Frame(self, bg=VERDE_OSCURO, width=215)
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)
        tk.Label(
            barra, text="YIELD MANAGER", font=("Segoe UI", 15, "bold"),
            fg="white", bg=VERDE_OSCURO
        ).pack(anchor="w", padx=18, pady=(22, 0))
        tk.Label(
            barra, text="Procesadora Don Juan", font=("Segoe UI", 9),
            fg="#b1caba", bg=VERDE_OSCURO
        ).pack(anchor="w", padx=18, pady=(2, 21))

        self.botones_nav = {}

        def titulo_grupo(texto):
            tk.Label(
                barra, text=texto, font=("Segoe UI", 8, "bold"),
                fg="#91b09c", bg=VERDE_OSCURO
            ).pack(anchor="w", padx=18, pady=(13, 5))

        def boton_pagina(nombre):
            boton = tk.Button(
                barra, text=nombre, anchor="w",
                command=lambda pagina=nombre: self.mostrar_pagina(pagina),
                font=("Segoe UI", 10), fg="#e2eee6", bg=VERDE_OSCURO,
                activebackground="#285849", activeforeground="white",
                relief="flat", padx=15, pady=9, cursor="hand2"
            )
            boton.pack(fill="x", padx=8, pady=1)
            self.botones_nav[nombre] = boton

        titulo_grupo("INICIO")
        for nombre in ("Resumen", "Inventario"):
            boton_pagina(nombre)

        paginas = self._paginas_permitidas()
        if "Producción" in paginas:
            titulo_grupo("PRODUCCIÓN")
            boton_pagina("Producción")

        # Los botones de movimiento abren formularios sin cambiar de página.
        titulo_grupo("MOVIMIENTOS")
        acciones = []
        if self.usuario["role"] in ("Administrador", "Almacenista"):
            acciones.append(("Nueva entrada", self.abrir_entrada))
            acciones.append(("Registrar merma", self.abrir_merma))
            if "Producción" in paginas:
                acciones.append(("Registrar producción", self.abrir_transformacion))
        acciones.append(("Registrar salida", self.abrir_despacho))
        for texto, comando in acciones:
            boton = tk.Button(
                barra, text=f"＋  {texto}", anchor="w", command=comando,
                font=("Segoe UI", 9, "bold"), fg="#e2eee6", bg="#285849",
                activebackground="#356c57", activeforeground="white",
                relief="flat", padx=13, pady=8, cursor="hand2"
            )
            boton.pack(fill="x", padx=8, pady=2)

        grupos_admin = (
            ("ANÁLISIS", ("Reportes", "Actividad")),
            ("ADMINISTRACIÓN", ("Usuarios",)),
        )
        for grupo, nombres in grupos_admin:
            visibles = [nombre for nombre in nombres if nombre in paginas]
            if visibles:
                titulo_grupo(grupo)
                for nombre in visibles:
                    boton_pagina(nombre)

        tk.Button(
            barra, text="Cerrar sesión", command=self.app.cerrar_sesion,
            font=("Segoe UI", 9, "bold"), fg="white", bg="#285849",
            activebackground="#356c57", relief="flat", padx=10, pady=8
        ).pack(side="bottom", fill="x", padx=9, pady=(12, 0))
        tk.Label(
            barra, text=f"{self.usuario['name']}\n{self.usuario['role']}",
            font=("Segoe UI", 9), fg="#d4e5da", bg=VERDE_OSCURO,
            justify="left"
        ).pack(side="bottom", anchor="w", padx=16, pady=(5, 12))

        cuerpo = tk.Frame(self, bg=FONDO)
        cuerpo.pack(side="left", fill="both", expand=True)
        self.encabezado = tk.Frame(cuerpo, bg="white", height=52)
        self.encabezado.pack(fill="x")
        self.encabezado.pack_propagate(False)
        self.texto_encabezado = tk.Label(
            self.encabezado, text="Procesadora Don Juan / Resumen",
            font=("Segoe UI", 10), fg=TEXTO, bg="white"
        )
        self.texto_encabezado.pack(side="left", padx=22)
        tk.Label(
            self.encabezado, text=date.today().strftime("%d/%m/%Y"),
            font=("Segoe UI", 9), fg=SUAVE, bg="white"
        ).pack(side="right", padx=22)
        ttk.Button(
            self.encabezado, text="⚙ Ajustes",
            command=lambda: self.mostrar_pagina("Ajustes")
        ).pack(side="right", padx=(0, 12))
        self.area = tk.Frame(cuerpo, bg=FONDO)
        self.area.pack(fill="both", expand=True, padx=22, pady=20)

    def mostrar_pagina(self, nombre):
        """Cambia de pantalla o abre un formulario de operación."""
        acciones = {
            "Nueva entrada": self.abrir_entrada,
            "Registrar salida": self.abrir_despacho,
            "Registrar merma": self.abrir_merma,
            "Registrar producción": self.abrir_transformacion,
        }
        if nombre in acciones:
            if (
                nombre != "Registrar salida"
                and self.usuario["role"] not in ("Administrador", "Almacenista")
            ):
                return
            acciones[nombre]()
            return
        if nombre != "Ajustes" and nombre not in self._paginas_permitidas():
            return

        self.pagina_actual = nombre
        for elemento in self.area.winfo_children():
            elemento.destroy()
        for pagina, boton in self.botones_nav.items():
            color = "#285849" if pagina == nombre else VERDE_OSCURO
            texto = "white" if pagina == nombre else "#d4e5da"
            boton.configure(bg=color, fg=texto)
        self.texto_encabezado.configure(
            text=f"Procesadora Don Juan / {nombre}"
        )
        paginas = {
            "Resumen": self._pagina_resumen,
            "Inventario": self._pagina_inventario,
            "Producción": self._pagina_transformaciones,
            "Reportes": self._pagina_reportes,
            "Actividad": self._pagina_auditoria,
            "Usuarios": self._pagina_cuentas,
            "Ajustes": self._pagina_configuracion,
        }
        paginas[nombre]()

    def _titulo(self, titulo, descripcion, boton=None, accion=None):
        """Agrega el encabezado de cada pantalla."""
        fila = tk.Frame(self.area, bg=FONDO)
        fila.pack(fill="x", pady=(0, 14))
        texto = tk.Frame(fila, bg=FONDO)
        texto.pack(side="left", fill="x", expand=True)
        tk.Label(
            texto, text=titulo, font=("Segoe UI", 20, "bold"),
            fg=TEXTO, bg=FONDO
        ).pack(anchor="w")
        if descripcion:
            tk.Label(
                texto, text=descripcion, font=("Segoe UI", 9),
                fg=SUAVE, bg=FONDO
            ).pack(anchor="w", pady=(3, 0))
        if boton:
            ttk.Button(
                fila, text=boton, command=accion, style="Accent.TButton"
            ).pack(side="right")

    def _panel(self, padre=None):
        """Crea una tarjeta blanca para contener información."""
        return tk.Frame(
            padre or self.area, bg="white",
            highlightbackground=BORDE, highlightthickness=1
        )

    def _tabla(self, padre, columnas, encabezados, anchos=None):
        """Construye una tabla con barra de desplazamiento."""
        marco = tk.Frame(padre, bg="white")
        marco.pack(fill="both", expand=True)
        tabla = ttk.Treeview(
            marco, columns=columnas, show="headings", selectmode="browse"
        )
        for indice, (columna, titulo) in enumerate(zip(columnas, encabezados)):
            tabla.heading(columna, text=titulo)
            ancho = anchos[indice] if anchos else 110
            tabla.column(columna, width=ancho, minwidth=ancho, anchor="w")
        barra = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
        horizontal = ttk.Scrollbar(
            marco, orient="horizontal", command=tabla.xview
        )
        tabla.configure(
            yscrollcommand=barra.set, xscrollcommand=horizontal.set
        )
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        tabla.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tabla.tag_configure("Prioridad", foreground=ROJO)
        tabla.tag_configure("Próximo", foreground=AMARILLO)
        tabla.tag_configure("Vencido", foreground=ROJO)
        tabla.tag_configure("Seguro", foreground=VERDE)
        return tabla

    def _llenar_tabla(self, tabla, filas, estados=None):
        """Reemplaza las filas para mostrar los datos más recientes."""
        tabla.delete(*tabla.get_children())
        for indice, fila in enumerate(filas):
            estado = estados[indice] if estados else ""
            valores = list(fila)
            if estado == "Prioridad" and valores:
                valores[-1] = "Urgente"
            tabla.insert("", "end", values=valores, tags=(estado,))

    def _tarjeta_metrica(self, padre, titulo, valor, nota, color=VERDE):
        """Muestra una cifra importante en una tarjeta pequeña."""
        tarjeta = self._panel(padre)
        tarjeta.pack(side="left", fill="both", expand=True, padx=(0, 9))
        tk.Label(
            tarjeta, text=titulo, font=("Segoe UI", 9),
            fg=SUAVE, bg="white"
        ).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(
            tarjeta, text=valor, font=("Segoe UI", 21, "bold"),
            fg=color, bg="white"
        ).pack(anchor="w", padx=14, pady=1)
        tk.Label(
            tarjeta, text=nota, font=("Segoe UI", 8),
            fg=SUAVE, bg="white"
        ).pack(anchor="w", padx=14, pady=(0, 12))

    def _pagina_resumen(self):
        """Resume inventario y resalta las caducidades más cercanas."""
        lotes = self.base.lotes(self.usuario["id"])
        rol = self.usuario["role"]
        nombre_accion = "Registrar salida"
        accion = self.abrir_despacho
        if rol in ("Administrador", "Almacenista"):
            nombre_accion = "Nueva entrada"
            accion = self.abrir_entrada
        if rol == "Administrador" and not self.base.productos(self.usuario["id"]):
            nombre_accion = "Agregar producto"
            accion = self.abrir_producto

        # La acción principal ayuda a empezar sin buscarla en el menú.
        self._titulo(
            "Resumen de inventario",
            "Revisa existencias y fechas de caducidad.",
            nombre_accion, accion
        )
        tarjetas = tk.Frame(self.area, bg=FONDO)
        tarjetas.pack(fill="x", pady=(0, 14))
        # Cada lote queda agrupado según los días que faltan para caducar.
        estados = {
            nombre: sum(lote["state"] == nombre for lote in lotes)
            for nombre in ("Seguro", "Próximo", "Prioridad", "Vencido")
        }
        total = sum(lote["quantity"] for lote in lotes)
        self._tarjeta_metrica(
            tarjetas, "En buen estado", str(estados["Seguro"]),
            "Más de 7 días", VERDE
        )
        self._tarjeta_metrica(
            tarjetas, "Próximos a vencer", str(estados["Próximo"]),
            "De 4 a 7 días", AMARILLO
        )
        self._tarjeta_metrica(
            tarjetas, "Revisar hoy",
            str(estados["Prioridad"] + estados["Vencido"]),
            "Prioridad o vencidos", ROJO
        )
        self._tarjeta_metrica(
            tarjetas, "Disponible",
            f"{total:,.1f} kg" if total else "0 kg",
            f"{len(lotes)} lotes disponibles"
        )

        panel = self._panel()
        panel.pack(fill="both", expand=True)
        tk.Label(
            panel, text="Lotes por fecha de caducidad",
            font=("Segoe UI", 11, "bold"), bg="white", fg=TEXTO
        ).pack(anchor="w", padx=14, pady=12)
        tabla = self._tabla(
            panel,
            ("product", "code", "expiry", "days", "quantity", "location", "state"),
            ("Producto", "Lote", "Caducidad", "Días", "Disponible", "Ubicación", "Estado"),
            (165, 100, 105, 65, 105, 130, 95)
        )
        urgentes = sorted(
            lotes, key=lambda lote: (lote["expiry"], lote["received"])
        )[:10]
        filas = [
            (
                lote["product"], lote["code"], lote["expiry"],
                lote["days_left"], f"{lote['quantity']:g} kg",
                lote["location"], lote["state"]
            )
            for lote in urgentes
        ]
        self._llenar_tabla(
            tabla, filas, [lote["state"] for lote in urgentes]
        )
        if not lotes:
            tk.Label(
                panel,
                text="Aún no hay existencias. Registra una entrada para comenzar.",
                bg="white", fg=SUAVE, font=("Segoe UI", 10)
            ).pack(pady=(0, 18))

    def _pagina_inventario(self):
        """Busca lotes disponibles por nombre, código y operación."""
        puede_recibir = self.usuario["role"] in ("Administrador", "Almacenista")
        self._titulo(
            "Inventario", "Busca productos y revisa las cantidades disponibles.",
            "Nueva entrada" if puede_recibir else "Registrar salida",
            self.abrir_entrada if puede_recibir else self.abrir_despacho
        )
        panel = self._panel()
        panel.pack(fill="both", expand=True)
        filtros = tk.Frame(panel, bg="white")
        filtros.pack(fill="x", padx=14, pady=12)
        tk.Label(
            filtros, text="Producto o lote", font=("Segoe UI", 9, "bold"),
            fg=TEXTO, bg="white"
        ).pack(side="left", padx=(0, 6))
        self.variables_filtro["buscar"] = tk.StringVar()
        buscador = ttk.Entry(
            filtros, textvariable=self.variables_filtro["buscar"], width=26
        )
        buscador.pack(side="left", padx=(0, 14), ipady=4)
        tk.Label(
            filtros, text="Operación", font=("Segoe UI", 9, "bold"),
            fg=TEXTO, bg="white"
        ).pack(side="left", padx=(0, 6))
        self.variables_filtro["operacion"] = tk.StringVar(value="Todas")
        giro = ttk.Combobox(
            filtros, textvariable=self.variables_filtro["operacion"],
            values=("Todas", "Fábrica", "Reventa"),
            state="readonly", width=14
        )
        giro.pack(side="left")
        if self.usuario["role"] == "Administrador":
            ttk.Button(
                filtros, text="Agregar producto", command=self.abrir_producto,
                style="Accent.TButton"
            ).pack(side="right")
            ttk.Button(
                filtros, text="Eliminar producto",
                command=self.abrir_eliminar_producto,
                style="Danger.TButton"
            ).pack(side="right", padx=(0, 8))

        columnas = ("product", "giro", "code", "expiry", "quantity", "location", "state")
        encabezados = (
            "Producto", "Operación", "Lote", "Caducidad",
            "Disponible", "Ubicación", "Estado"
        )
        tabla = self._tabla(
            panel, columnas, encabezados, (175, 105, 105, 105, 105, 140, 95)
        )
        estado_vacio = tk.Label(
            panel, text="No se encontraron lotes para esta búsqueda.",
            bg="white", fg=SUAVE, font=("Segoe UI", 10)
        )

        def actualizar(*_):
            """Refresca la tabla con los filtros elegidos."""
            tipo = self.variables_filtro["operacion"].get()
            lotes = self.base.lotes(
                self.usuario["id"],
                self.variables_filtro["buscar"].get(),
                "" if tipo == "Todas" else tipo,
            )
            filas = [
                (
                    lote["product"], lote["giro"], lote["code"],
                    lote["expiry"], f"{lote['quantity']:g} kg",
                    lote["location"], lote["state"]
                )
                for lote in lotes
            ]
            self._llenar_tabla(
                tabla, filas, [lote["state"] for lote in lotes]
            )
            if lotes:
                estado_vacio.pack_forget()
            elif not estado_vacio.winfo_ismapped():
                estado_vacio.pack(pady=12)

        self.variables_filtro["buscar"].trace_add("write", actualizar)
        giro.bind("<<ComboboxSelected>>", actualizar)
        actualizar()

    def _pagina_transformaciones(self):
        """Muestra los procesos de fabricación y su rendimiento."""
        self._titulo(
            "Producción",
            "Consulta lo producido, el rendimiento y las pérdidas del proceso.",
            "Registrar producción", self.abrir_transformacion
        )
        registros = self.base.transformaciones(self.usuario["id"])
        panel = self._panel()
        panel.pack(fill="both", expand=True)
        tabla = self._tabla(
            panel,
            ("at", "input_product", "input_qty", "output_product",
             "output_qty", "yield", "waste"),
            ("Fecha", "Materia prima", "Kg usados", "Producto final",
             "Kg obtenidos", "Rendimiento", "Merma")
        )
        filas = [
            (
                fila["at"][:10], fila["input_product"],
                f"{fila['input_qty']:g}", fila["output_product"],
                f"{fila['output_qty']:g}", f"{fila['yield']:.1f}%",
                f"{fila['technical_waste']:g} kg"
            )
            for fila in registros
        ]
        self._llenar_tabla(tabla, filas)
        if not filas:
            tk.Label(
                panel, text="Aún no hay producción registrada.",
                bg="white", fg=SUAVE
            ).pack(pady=15)

    def _pagina_reportes(self):
        """Presenta las existencias y permite exportarlas."""
        self._titulo(
            "Reportes", "Existencias actuales y productos bajo mínimo."
        )
        datos = self.base.reporte_productos(self.usuario["id"])
        lotes = self.base.lotes(self.usuario["id"])
        tarjetas = tk.Frame(self.area, bg=FONDO)
        tarjetas.pack(fill="x", pady=(0, 12))
        total = sum(lote["quantity"] for lote in lotes)
        self._tarjeta_metrica(
            tarjetas, "Existencia total", f"{total:.1f} kg",
            "Cantidad en lotes disponibles"
        )
        self._tarjeta_metrica(
            tarjetas, "Lotes disponibles", str(len(lotes)),
            "Con cantidad disponible"
        )
        self._tarjeta_metrica(
            tarjetas, "Merma registrada",
            f"{self.base.total_merma(self.usuario['id']):.1f} kg",
            "Cantidad acumulada", ROJO
        )

        panel = self._panel()
        panel.pack(fill="both", expand=True)
        botones = tk.Frame(panel, bg="white")
        botones.pack(fill="x", padx=12, pady=10)
        ttk.Button(
            botones, text="Exportar CSV", command=self._exportar_csv
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            botones, text="Imprimir o guardar PDF",
            command=self._imprimir_reporte
        ).pack(side="right")
        tabla = self._tabla(
            panel,
            ("name", "giro", "quantity", "lots", "minimum", "state"),
            ("Producto", "Operación", "Existencia kg", "Lotes",
             "Mínimo kg", "Estado")
        )
        filas = [
            (
                dato["name"], dato["giro"], f"{dato['quantity']:.1f}",
                dato["lots"], f"{dato['minimum']:g}", dato["state"]
            )
            for dato in datos
        ]
        self._llenar_tabla(tabla, filas)

    def _pagina_auditoria(self):
        """Muestra las entradas, salidas y ajustes recientes."""
        self._titulo(
            "Actividad", "Entradas, salidas y ajustes recientes."
        )
        movimientos = self.base.movimientos(self.usuario["id"])
        panel = self._panel()
        panel.pack(fill="both", expand=True)
        tabla = self._tabla(
            panel,
            ("at", "kind", "product", "lot", "quantity", "detail"),
            ("Fecha", "Movimiento", "Producto", "Lote", "Cantidad kg", "Detalle"),
            (145, 120, 160, 100, 105, 240)
        )
        filas = [
            (
                fila["at"], fila["kind"], fila["product"], fila["lot"],
                f"{fila['quantity']:g}", fila["detail"]
            )
            for fila in movimientos
        ]
        self._llenar_tabla(tabla, filas)

    def _pagina_cuentas(self):
        """Permite cambiar el rol o el acceso de cada cuenta."""
        self._titulo(
            "Usuarios", "Administra quién puede acceder a la aplicación."
        )
        panel = self._panel()
        panel.pack(fill="both", expand=True)
        tabla = self._tabla(
            panel,
            ("id", "name", "email", "role", "verified", "active"),
            ("ID", "Nombre", "Correo", "Rol", "Verificado", "Activo")
        )
        tabla.column("id", width=0, minwidth=0, stretch=False)
        usuarios = self.base.usuarios()
        filas = [
            (
                fila["id"], fila["name"], fila["email"], fila["role"],
                "Sí" if fila["verified"] else "No",
                "Sí" if fila["active"] else "No"
            )
            for fila in usuarios
        ]
        self._llenar_tabla(tabla, filas)

        controles = tk.Frame(panel, bg="white")
        controles.pack(fill="x", padx=12, pady=12)
        rol = tk.StringVar(value="Almacenista")
        ttk.Combobox(
            controles, textvariable=rol, values=ROLES,
            state="readonly", width=18
        ).pack(side="left", padx=(0, 8))
        activo = tk.BooleanVar(value=True)
        tk.Checkbutton(
            controles, text="Cuenta activa", variable=activo,
            bg="white", selectcolor="white"
        ).pack(side="left", padx=5)

        def cargar_seleccion(_=None):
            """Carga los valores de la cuenta elegida."""
            seleccion = tabla.selection()
            if not seleccion:
                return
            id_usuario = int(tabla.item(seleccion[0], "values")[0])
            cuenta = next(
                (fila for fila in usuarios if fila["id"] == id_usuario), None
            )
            if cuenta:
                rol.set(cuenta["role"])
                activo.set(bool(cuenta["active"]))

        def guardar_cambios():
            """Guarda el rol y estado elegidos por el administrador."""
            seleccion = tabla.selection()
            if not seleccion:
                messagebox.showinfo(
                    "Elige una cuenta", "Selecciona una fila de la tabla."
                )
                return
            id_usuario = int(tabla.item(seleccion[0], "values")[0])
            cuenta = next(
                (fila for fila in usuarios if fila["id"] == id_usuario), None
            )
            if (
                cuenta
                and cuenta["email"] == self.usuario["email"]
                and (rol.get() != "Administrador" or not activo.get())
            ):
                messagebox.showerror(
                    "No se puede cambiar",
                    "Mantén tu cuenta activa como Administrador."
                )
                return
            try:
                self.base.cambiar_usuario(id_usuario, rol.get(), activo.get())
            except ValueError as error:
                messagebox.showerror("No se pudo guardar", str(error))
                return
            self.mostrar_pagina("Usuarios")

        tabla.bind("<<TreeviewSelect>>", cargar_seleccion)
        ttk.Button(
            controles, text="Guardar cambios", command=guardar_cambios
        ).pack(side="right")

    def _pagina_configuracion(self):
        """Reúne los ajustes de acceso en una pantalla breve."""
        self._titulo(
            "Ajustes", "Administra tu cuenta y el correo de verificación."
        )
        panel = self._panel()
        panel.pack(fill="x", pady=(0, 12))
        tk.Label(
            panel, text="Tu cuenta", bg="white", fg=TEXTO,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(
            panel, text=f"{self.usuario['email']}  ·  {self.usuario['role']}",
            bg="white", fg=SUAVE, font=("Segoe UI", 10)
        ).pack(anchor="w", padx=16, pady=(0, 14))

        if self.usuario["role"] == "Administrador":
            correo = self._panel()
            correo.pack(fill="x", pady=(0, 12))
            tk.Label(
                correo, text="Correo de verificación", bg="white", fg=TEXTO,
                font=("Segoe UI", 11, "bold")
            ).pack(anchor="w", padx=16, pady=(14, 4))
            estado = "Configurado" if self.app.correo_configurado() else "Pendiente"
            tk.Label(
                correo, text=estado, bg="white",
                fg=VERDE if estado == "Configurado" else AMARILLO,
                font=("Segoe UI", 10)
            ).pack(anchor="w", padx=16, pady=(0, 10))
            ttk.Button(
                correo, text="Configurar correo",
                command=lambda: self.app.mostrar_correo("principal")
            ).pack(anchor="w", padx=16, pady=(0, 14))

        eliminar = self._panel()
        eliminar.pack(fill="x")
        tk.Label(
            eliminar, text="Eliminar cuenta", bg="white", fg=TEXTO,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(
            eliminar, text="También se eliminará el inventario de esta cuenta.",
            bg="white", fg=SUAVE, font=("Segoe UI", 9)
        ).pack(anchor="w", padx=16, pady=(0, 10))
        tk.Button(
            eliminar, text="Eliminar cuenta", command=self._eliminar_cuenta,
            font=("Segoe UI", 9, "bold"), fg="white", bg=ROJO,
            activebackground="#942f2a", activeforeground="white",
            relief="flat", cursor="hand2", padx=12, pady=8
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _eliminar_cuenta(self):
        """Pide confirmación y elimina solo la cuenta activa."""
        confirmar = messagebox.askyesno(
            "Eliminar cuenta",
            f"¿Eliminar la cuenta {self.usuario['email']}?\n\n"
            "También se eliminarán su inventario, lotes, movimientos y transformaciones. "
            "Los datos de las demás cuentas no cambiarán. Esta acción no se puede deshacer.",
            icon="warning", parent=self
        )
        if not confirmar:
            return
        try:
            self.base.eliminar_cuenta(self.usuario["id"])
        except ValueError as error:
            messagebox.showerror("No se pudo eliminar", str(error), parent=self)
            return

        self.app._borrar_sesion_guardada()
        self.app.usuario = None
        self.app.mostrar_inicio(
            "La cuenta y sus datos se eliminaron. Las demás cuentas no cambiaron."
        )

    def abrir_producto(self):
        """Pide los datos para agregar un producto al catálogo."""
        categorias = [
            ("Res", "Res"), ("Cerdo", "Cerdo"), ("Aves", "Aves"),
            ("Embutidos", "Embutidos"), ("Otros", "Otros")
        ]
        giros = [("Fábrica", "Fábrica"), ("Reventa", "Reventa")]
        campos = [
            ("nombre", "Nombre del producto", "texto", None, ""),
            ("categoria", "Categoría", "lista", categorias, None),
            ("giro", "Tipo de operación", "lista", giros, None),
            ("minimo", "Stock mínimo en kg", "texto", None, "0")
        ]

        def guardar(datos):
            """Guarda el producto y vuelve al inventario."""
            self.base.crear_producto(
                self.usuario["id"],
                datos["nombre"], datos["categoria"], datos["giro"],
                datos["minimo"], "kg", self.usuario["email"]
            )
            self.mostrar_pagina("Inventario")

        Formulario(self, "Nuevo producto", campos, guardar)

    def abrir_eliminar_producto(self):
        """Permite elegir y eliminar un producto de esta cuenta."""
        if self.usuario["role"] != "Administrador":
            return
        productos = self.base.productos(self.usuario["id"])
        if not productos:
            messagebox.showinfo("Sin productos", "No hay productos para eliminar.")
            return

        opciones = [(producto["name"], producto["id"]) for producto in productos]

        def eliminar(datos):
            """Confirma el borrado y refresca el inventario."""
            producto = next(
                (fila for fila in productos if fila["id"] == datos["producto"]),
                None,
            )
            if not producto:
                messagebox.showerror("Producto no disponible", "Vuelve a abrir la lista.")
                return
            confirmar = messagebox.askyesno(
                "Eliminar producto",
                f"¿Eliminar {producto['name']} y todos sus lotes?\n\n"
                "Se quitarán también las cantidades disponibles. El historial "
                "de movimientos se conservará.",
                icon="warning", parent=self,
            )
            if not confirmar:
                return
            self.base.eliminar_producto(
                self.usuario["id"], datos["producto"], self.usuario["email"]
            )
            self.mostrar_pagina("Inventario")
            messagebox.showinfo("Producto eliminado", "El producto se quitó del inventario.")

        Formulario(
            self, "Eliminar producto",
            [("producto", "Producto", "lista", opciones, None)],
            eliminar,
        )

    def abrir_entrada(self):
        """Registra un lote recibido y su fecha de caducidad."""
        productos = self.base.productos(self.usuario["id"])
        if not productos:
            messagebox.showinfo(
                "Primero crea un producto",
                "Agrega un producto antes de registrar su entrada."
            )
            self.abrir_producto()
            return
        opciones = [
            (f"{p['name']} · {p['giro']}", p["id"])
            for p in productos
        ]
        caducidad = (date.today() + timedelta(days=10)).isoformat()
        campos = [
            ("producto", "Producto", "lista", opciones, None),
            ("caducidad", "Caducidad (AAAA-MM-DD)", "texto", None, caducidad),
            ("cantidad", "Cantidad recibida en kg", "texto", None, ""),
            ("ubicacion", "Ubicación física", "texto", None, "")
        ]

        def guardar(datos):
            """Crea el lote y actualiza la bitácora."""
            self.base.registrar_entrada(
                self.usuario["id"],
                datos["producto"], datos["caducidad"], datos["cantidad"],
                datos["ubicacion"], self.usuario["email"]
            )
            self.mostrar_pagina("Resumen")

        Formulario(self, "Registrar entrada", campos, guardar)

    def abrir_despacho(self):
        """Sugiere el lote más antiguo disponible según PEPS."""
        lotes = [
            lote for lote in self.base.lotes(self.usuario["id"])
            if lote["days_left"] >= 0
        ]
        if not lotes:
            messagebox.showinfo(
                "Sin inventario", "No hay lotes vigentes para despachar."
            )
            return
        opciones = [
            (
                f"{lote['code']} · {lote['product']} · "
                f"{lote['quantity']:g} kg · ingreso {lote['received']}",
                lote["id"]
            )
            for lote in lotes
        ]
        campos = [
            ("lote", "Lote más antiguo disponible", "lista", opciones, None),
            ("cantidad", "Cantidad a retirar en kg", "texto", None, ""),
            ("cliente", "Cliente o destino", "texto", None, "")
        ]

        def guardar(datos):
            """Registra la salida y el destino de la mercancía."""
            self.base.descontar_lote(
                self.usuario["id"],
                datos["lote"], datos["cantidad"], "Despacho",
                f"Destino: {datos['cliente']}", self.usuario["email"]
            )
            self.mostrar_pagina("Resumen")

        Formulario(self, "Registrar salida", campos, guardar)

    def abrir_merma(self):
        """Registra un lote afectado y la cantidad perdida."""
        lotes = self.base.lotes(self.usuario["id"])
        if not lotes:
            messagebox.showinfo(
                "Sin inventario", "No hay lotes disponibles para registrar."
            )
            return
        opciones = [
            (
                f"{lote['code']} · {lote['product']} · "
                f"{lote['quantity']:g} kg",
                lote["id"]
            )
            for lote in lotes
        ]
        causas = [
            ("Caducidad", "Caducidad"),
            ("Empaque dañado", "Empaque dañado"),
            ("Contaminación", "Contaminación"),
            ("Otra causa", "Otra causa")
        ]
        campos = [
            ("lote", "Lote afectado", "lista", opciones, None),
            ("cantidad", "Cantidad perdida en kg", "texto", None, ""),
            ("causa", "Causa", "lista", causas, None)
        ]

        def guardar(datos):
            """Descuenta la merma y deja su causa en la bitácora."""
            self.base.descontar_lote(
                self.usuario["id"],
                datos["lote"], datos["cantidad"], "Merma",
                f"Causa: {datos['causa']}", self.usuario["email"]
            )
            self.mostrar_pagina("Resumen")

        Formulario(self, "Registrar merma", campos, guardar)

    def abrir_transformacion(self):
        """Convierte un lote de materia prima en producto terminado."""
        lotes = [
            lote for lote in self.base.lotes(
                self.usuario["id"], giro="Fábrica"
            )
            if lote["days_left"] >= 0
        ]
        productos = [
            producto for producto in self.base.productos(self.usuario["id"])
            if producto["giro"] == "Fábrica"
        ]
        if not lotes or not productos:
            messagebox.showinfo(
                "Falta inventario",
                "Agrega productos y lotes de Fábrica antes de transformar."
            )
            return

        opciones_lotes = [
            (
                f"{lote['code']} · {lote['product']} · "
                f"{lote['quantity']:g} kg",
                lote["id"]
            )
            for lote in lotes
        ]
        opciones_productos = [
            (producto["name"], producto["id"])
            for producto in productos
        ]
        caducidad = (date.today() + timedelta(days=7)).isoformat()
        campos = [
            ("lote", "Materia prima", "lista", opciones_lotes, None),
            ("entrada", "Peso de entrada en kg", "texto", None, ""),
            ("producto", "Producto terminado", "lista",
             opciones_productos, None),
            ("salida", "Peso obtenido en kg", "texto", None, ""),
            ("caducidad", "Caducidad (AAAA-MM-DD)", "texto", None, caducidad)
        ]

        def guardar(datos):
            """Guarda el lote nuevo y el rendimiento obtenido."""
            self.base.registrar_transformacion(
                self.usuario["id"],
                datos["lote"], datos["entrada"], datos["producto"],
                datos["salida"], datos["caducidad"], self.usuario["email"]
            )
            self.mostrar_pagina("Producción")

        Formulario(self, "Registrar producción", campos, guardar)

    def _exportar_csv(self):
        """Exporta los lotes a un archivo que Excel puede abrir."""
        ruta = filedialog.asksaveasfilename(
            title="Exportar inventario",
            defaultextension=".csv",
            filetypes=(("Archivo CSV", "*.csv"),),
            initialfile="inventario-yield-manager.csv"
        )
        if not ruta:
            return
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(
                [
                    "Producto", "Operación", "Lote", "Ingreso", "Caducidad",
                    "Cantidad kg", "Ubicación", "Estado"
                ]
            )
            for lote in self.base.lotes(self.usuario["id"]):
                escritor.writerow(
                    [
                        lote["product"], lote["giro"], lote["code"],
                        lote["received"], lote["expiry"], lote["quantity"],
                        lote["location"], lote["state"]
                    ]
                )
        messagebox.showinfo(
            "Reporte exportado", f"Archivo guardado en:\n{ruta}"
        )

    def _imprimir_reporte(self):
        """Crea un reporte para imprimir o guardar como PDF."""
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte para imprimir",
            defaultextension=".html",
            filetypes=(("Reporte HTML", "*.html"),),
            initialfile="reporte-yield-manager.html"
        )
        if not ruta:
            return
        filas = []
        for dato in self.base.reporte_productos(self.usuario["id"]):
            filas.append(
                "<tr>"
                f"<td>{html.escape(dato['name'])}</td>"
                f"<td>{html.escape(dato['giro'])}</td>"
                f"<td>{dato['quantity']:.1f} kg</td>"
                f"<td>{dato['minimum']:g} kg</td>"
                f"<td>{html.escape(dato['state'])}</td>"
                "</tr>"
            )

        reporte = f"""<!doctype html>
        <html lang="es">
        <meta charset="utf-8">
        <title>Reporte Yield Manager</title>
        <style>
          body {{ font: 14px Arial, sans-serif; margin: 32px; color: #1c2d26; }}
          h1 {{ color: #164b3b; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border: 1px solid #dfe8e1; padding: 8px; text-align: left; }}
          th {{ background: #edf2ee; }}
        </style>
        <h1>Procesadora Don Juan · Yield Manager</h1>
        <p>Inventario · {date.today().strftime('%d/%m/%Y')}</p>
        <button onclick="window.print()">Imprimir o guardar como PDF</button>
        <table>
          <tr><th>Producto</th><th>Operación</th><th>Existencia</th>
          <th>Mínimo</th><th>Estado</th></tr>
          {''.join(filas)}
        </table>
        </html>"""
        Path(ruta).write_text(reporte, encoding="utf-8")
        webbrowser.open(Path(ruta).resolve().as_uri())


if __name__ == "__main__":
    programa = Aplicacion()
    programa.mainloop()
