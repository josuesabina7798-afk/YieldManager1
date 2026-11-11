"""Herramientas sencillas para proteger cuentas y enviar correo."""

import base64
import ctypes
import hashlib
import hmac
import os
import re
import smtplib
import ssl
from ctypes import wintypes
from email.message import EmailMessage


# PBKDF2 hace que probar muchas contraseñas sea más lento.
ITERACIONES_PASSWORD = 600_000
ITERACIONES_CODIGO = 150_000


def correo_valido(correo):
    """Comprueba que el correo tenga una forma básica válida."""
    patron = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.fullmatch(patron, correo.strip()) is not None


def crear_hash_password(password):
    """Devuelve la sal y el hash que se guardan en la base de datos."""
    sal = os.urandom(16)
    clave = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal, ITERACIONES_PASSWORD
    )
    return sal.hex(), clave.hex()


def verificar_password(password, sal_hex, hash_guardado):
    """Compara la contraseña escrita con el hash protegido."""
    sal = bytes.fromhex(sal_hex)
    clave = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal, ITERACIONES_PASSWORD
    )
    return hmac.compare_digest(clave.hex(), hash_guardado)


def crear_hash_codigo(codigo, sal):
    """Guarda el código como hash para que no quede visible en SQLite."""
    clave = hashlib.pbkdf2_hmac(
        "sha256", codigo.encode("utf-8"), sal, ITERACIONES_CODIGO
    )
    return clave.hex()


def crear_codigo():
    """Crea un código numérico aleatorio de seis dígitos."""
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"


class _BloqueDatos(ctypes.Structure):
    """Estructura que Windows usa para recibir datos protegidos."""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def proteger_dato(texto):
    """Cifra texto con Windows para que solo lo lea esta cuenta de usuario."""
    if os.name != "nt":
        raise RuntimeError("El guardado seguro requiere Windows.")

    datos = texto.encode("utf-8")
    entrada_buffer = ctypes.create_string_buffer(datos)
    entrada = _BloqueDatos(
        len(datos), ctypes.cast(entrada_buffer, ctypes.POINTER(ctypes.c_byte))
    )
    salida = _BloqueDatos()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_BloqueDatos), wintypes.LPCWSTR,
        ctypes.POINTER(_BloqueDatos), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_BloqueDatos)
    ]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    correcto = crypt32.CryptProtectData(
        ctypes.byref(entrada),
        "Yield Manager",
        None,
        None,
        None,
        0x1,
        ctypes.byref(salida),
    )
    if not correcto:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


def revelar_dato(datos_cifrados):
    """Descifra con Windows un valor protegido anteriormente."""
    if os.name != "nt":
        raise RuntimeError("El guardado seguro requiere Windows.")

    entrada_buffer = ctypes.create_string_buffer(datos_cifrados)
    entrada = _BloqueDatos(
        len(datos_cifrados),
        ctypes.cast(entrada_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    salida = _BloqueDatos()
    descripcion = wintypes.LPWSTR()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_BloqueDatos), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_BloqueDatos), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_BloqueDatos)
    ]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    correcto = crypt32.CryptUnprotectData(
        ctypes.byref(entrada),
        ctypes.byref(descripcion),
        None,
        None,
        None,
        0x1,
        ctypes.byref(salida),
    )
    if not correcto:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        return ctypes.string_at(salida.pbData, salida.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(salida.pbData)
        if descripcion:
            kernel32.LocalFree(ctypes.cast(descripcion, ctypes.c_void_p))


def enviar_correo(configuracion, destinatario, asunto, contenido):
    """Envía un mensaje con el servidor SMTP configurado por el usuario."""
    mensaje = EmailMessage()
    mensaje["From"] = configuracion["remitente"]
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(contenido)

    servidor = configuracion["servidor"]
    puerto = int(configuracion["puerto"])
    contexto = ssl.create_default_context()

    if configuracion["seguridad"] == "SSL":
        conexion = smtplib.SMTP_SSL(
            servidor, puerto, timeout=20, context=contexto
        )
    else:
        conexion = smtplib.SMTP(servidor, puerto, timeout=20)

    with conexion:
        conexion.ehlo()
        if configuracion["seguridad"] == "STARTTLS":
            conexion.starttls(context=contexto)
            conexion.ehlo()

        usuario = configuracion.get("usuario", "").strip()
        clave = configuracion.get("clave", "")
        if usuario:
            conexion.login(usuario, clave)

        conexion.send_message(mensaje)


def enviar_codigo(configuracion, destinatario, codigo):
    """Prepara el mensaje con el código temporal de registro."""
    asunto = "Código de seguridad de Yield Manager"
    contenido = (
        f"Usa este código para verificar tu cuenta: {codigo}\n\n"
        "El código vence en 10 minutos y solo se puede usar una vez.\n"
        "Si no solicitaste este código, puedes ignorar este mensaje."
    )
    enviar_correo(configuracion, destinatario, asunto, contenido)


def enviar_correo_prueba(configuracion):
    """Confirma que el servidor de correo acepta la configuración."""
    destinatario = configuracion["remitente"]
    enviar_correo(
        configuracion,
        destinatario,
        "Prueba de correo de Yield Manager",
        "La configuración SMTP de Yield Manager funciona correctamente.",
    )
