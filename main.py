import telebot
from telebot import types
import sqlite3
import time
import threading
import hashlib
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, redirect

# Conexión con mi bot
TOKEN = '7801919819:AAGI4LsC09YYBGI0qr2rw4hzUoWnlx7KuPc'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Función para crear las tablas si no existen
def crear_tablas():
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS canales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_canal TEXT NOT NULL,
                enlace_invitacion TEXT NOT NULL,
                descripcion TEXT,
                miembros_iniciales INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                clicks INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enlaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canal_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                enlace TEXT NOT NULL,
                fecha_creacion TEXT NOT NULL,
                clicks_recibidos INTEGER DEFAULT 0,
                nuevos_seguidores INTEGER DEFAULT 0,
                FOREIGN KEY (canal_id) REFERENCES canales (id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (chat_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                chat_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suscripciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                canal_id INTEGER,
                fecha_suscripcion TIMESTAMP
            )
        ''')
        conn.commit()

# Función para insertar un canal en la base de datos
def insert_canal(nombre_canal: str, enlace_invitacion: str, descripcion: str, miembros_iniciales: int, chat_id: int):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO canales (nombre_canal, enlace_invitacion, descripcion, miembros_iniciales, chat_id) VALUES (?, ?, ?, ?, ?)", 
                       (nombre_canal, enlace_invitacion, descripcion, miembros_iniciales, chat_id))
        conn.commit()

# Función para insertar un enlace en la base de datos
def insert_enlace(canal_id: int, usuario_id: int, enlace: str, fecha_creacion: str):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO enlaces (canal_id, usuario_id, enlace, fecha_creacion, clicks_recibidos, nuevos_seguidores) VALUES (?, ?, ?, ?, 0, 0)", 
                       (canal_id, usuario_id, enlace, fecha_creacion))
        conn.commit()

# Función para actualizar los clics recibidos de un enlace
def actualizar_clicks_enlace(enlace: str):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE enlaces SET clicks_recibidos = clicks_recibidos + 1 WHERE enlace = ?", (enlace,))
        conn.commit()

# Función para actualizar los nuevos seguidores de un enlace
def actualizar_nuevos_seguidores(canal_id: int):
    try:
        with sqlite3.connect('telegram_bot.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM canales WHERE id = ?", (canal_id,))
            chat_id = cursor.fetchone()[0]
            miembros_actuales = bot.get_chat_members_count(chat_id)
            cursor.execute("SELECT miembros_iniciales FROM canales WHERE id = ?", (canal_id,))
            miembros_iniciales = cursor.fetchone()[0]
            nuevos_seguidores = miembros_actuales - miembros_iniciales
            cursor.execute("UPDATE enlaces SET nuevos_seguidores = ? WHERE canal_id = ?", (nuevos_seguidores, canal_id))
            conn.commit()
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error al actualizar nuevos seguidores para el canal {canal_id}: {e}")

# Función para obtener el resumen de estadísticas de los enlaces de un usuario
def obtener_resumen_estadisticas(chat_id: int):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre_canal, enlace, clicks_recibidos, nuevos_seguidores FROM enlaces JOIN canales ON enlaces.canal_id = canales.id WHERE enlaces.usuario_id = ?", (chat_id,))
        resumen = cursor.fetchall()
    return resumen

# Función para enviar el reporte diario al usuario que lo solicita
def enviar_reporte_diario(chat_id):
    resumen = obtener_resumen_estadisticas(chat_id)
    mensaje = "Resumen diario de estadísticas:\n\n"
    for canal, enlace, clicks, seguidores in resumen:
        mensaje += f"Canal: {canal}\nEnlace: {enlace}\nClics recibidos: {clicks}\nNuevos seguidores: {seguidores}\n\n"
    bot.send_message(chat_id, mensaje)

# Función para registrar un usuario
def registrar_usuario(chat_id: int, username: str, password: str):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO usuarios (chat_id, username, password) VALUES (?, ?, ?)", (chat_id, username, hashed_password))
        conn.commit()

# Función para autenticar un usuario
def autenticar_usuario(chat_id: int, username: str, password: str):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE chat_id = ? AND username = ? AND password = ?", (chat_id, username, hashed_password))
        user = cursor.fetchone()
    return user is not None

# Función para verificar si un usuario está autenticado
def usuario_autenticado(chat_id: int):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()
    return user is not None

# Función para mostrar el menú principal
def mostrar_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_registrar = types.KeyboardButton('/registrar')
    btn_login = types.KeyboardButton('/login')
    btn_generar_enlace = types.KeyboardButton('/generar_enlace')
    btn_reporte = types.KeyboardButton('/reporte')
    markup.add(btn_registrar, btn_login, btn_generar_enlace, btn_reporte)
    bot.send_message(chat_id, "Selecciona una opción:", reply_markup=markup)

# Comando /start: envía un mensaje de bienvenida y muestra el menú principal
@bot.message_handler(commands=['start'])
def send_welcome(message):
    mensaje_bienvenida = (
        "Hola, soy tu bot generador de enlaces de invitación.\n\n"
        "Para poder utilizarme, primero debes registrarte con el comando /registrar seguido de tu nombre de usuario y contraseña.\n"
        "Si ya estás registrado, inicia sesión con el comando /login seguido de tu nombre de usuario y contraseña.\n\n"
        "Funciones disponibles:\n"
        "- /generar_enlace: Genera un enlace de invitación y lo almacena en la base de datos.\n"
        "- /reporte: Envía un reporte diario con un resumen de las estadísticas de todos los enlaces.\n"
    )
    bot.send_message(message.chat.id, mensaje_bienvenida)
    mostrar_menu(message.chat.id)

# Comando /reporte: envía el reporte diario al usuario que lo solicita
@bot.message_handler(commands=['reporte'])
def enviar_reporte_usuario(message):
    if usuario_autenticado(message.chat.id):
        enviar_reporte_diario(message.chat.id)
    else:
        bot.send_message(message.chat.id, "Debes estar registrado y logueado para usar este comando.")

# Función para manejar el registro de usuarios
def solicitar_usuario(message):
    msg = bot.send_message(message.chat.id, "Por favor, proporciona un nombre de usuario:")
    bot.register_next_step_handler(msg, solicitar_contraseña)

def solicitar_contraseña(message):
    username = message.text
    msg = bot.send_message(message.chat.id, "Por favor, proporciona una contraseña:")
    bot.register_next_step_handler(msg, registrar_usuario_final, username)

def registrar_usuario_final(message, username):
    password = message.text
    try:
        registrar_usuario(message.chat.id, username, password)
        bot.send_message(message.chat.id, "Registro exitoso.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Error al registrar: {e}")

# Comando /registrar: permite a los usuarios registrarse con un nombre de usuario y contraseña
@bot.message_handler(commands=['registrar'])
def registrar(message):
    solicitar_usuario(message)

# Función para manejar el inicio de sesión de usuarios
def solicitar_usuario_login(message):
    msg = bot.send_message(message.chat.id, "Por favor, proporciona tu nombre de usuario:")
    bot.register_next_step_handler(msg, solicitar_contraseña_login)

def solicitar_contraseña_login(message):
    username = message.text
    msg = bot.send_message(message.chat.id, "Por favor, proporciona tu contraseña:")
    bot.register_next_step_handler(msg, autenticar_usuario_final, username)

def autenticar_usuario_final(message, username):
    password = message.text
    try:
        if autenticar_usuario(message.chat.id, username, password):
            bot.send_message(message.chat.id, "Autenticación exitosa.")
        else:
            bot.send_message(message.chat.id, "Nombre de usuario o contraseña incorrectos.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Error al autenticar: {e}")

# Comando /login: permite a los usuarios autenticarse con su nombre de usuario y contraseña
@bot.message_handler(commands=['login'])
def login(message):
    solicitar_usuario_login(message)

# Función para manejar la generación de enlaces
def solicitar_enlace_canal(message):
    msg = bot.send_message(message.chat.id, "Por favor, reenvía un mensaje del canal del cual deseas generar el enlace:")
    bot.register_next_step_handler(msg, solicitar_mensaje)

def solicitar_mensaje(message):
    if not message.forward_from_chat:
        bot.send_message(message.chat.id, "Por favor, reenvía un mensaje válido del canal.")
        return
    
    chat_id = message.forward_from_chat.id
    canal_nombre = message.forward_from_chat.title if message.forward_from_chat.title else "Canal sin nombre"
    msg = bot.send_message(message.chat.id, "Por favor, proporciona un mensaje que acompañe al enlace:")
    bot.register_next_step_handler(msg, generar_enlace_final, chat_id, canal_nombre)

def generar_enlace_final(message, chat_id, canal_nombre):
    descripcion = message.text
    try:
        # Validar que el chat_id sea un entero
        try:
            chat_id = int(chat_id)
        except ValueError:
            bot.send_message(message.chat.id, "El ID del chat no es válido.")
            return
        
        # Recordatorio para poner al bot como administrador del canal o grupo
        bot.send_message(message.chat.id, "Asegúrate de que el bot sea administrador del canal o grupo para poder generar enlaces de invitación.")
        
        # Generar un enlace de invitación válido utilizando la API de Telegram
        try:
            enlace_invitacion = bot.export_chat_invite_link(chat_id)
        except telebot.apihelper.ApiTelegramException as e:
            bot.send_message(message.chat.id, f"Error al generar el enlace de invitación: {e}")
            return
        
        # Obtener el número de miembros iniciales del canal
        try:
            miembros_iniciales = bot.get_chat_members_count(chat_id)
        except telebot.apihelper.ApiTelegramException as e:
            bot.send_message(message.chat.id, f"Error al obtener el número de miembros del canal: {e}")
            return
        
        # Insertar en la base de datos
        with sqlite3.connect('telegram_bot.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO canales (nombre_canal, enlace_invitacion, descripcion, miembros_iniciales, chat_id) VALUES (?, ?, ?, ?, ?)", 
                           (canal_nombre, enlace_invitacion, descripcion, miembros_iniciales, chat_id))
            conn.commit()
            
            # Obtener el ID del canal
            cursor.execute("SELECT id FROM canales WHERE chat_id = ?", (chat_id,))
            canal_id = cursor.fetchone()[0]
            
            # Insertar el enlace en la tabla enlaces
            fecha_creacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO enlaces (canal_id, usuario_id, enlace, fecha_creacion, clicks_recibidos, nuevos_seguidores) VALUES (?, ?, ?, ?, 0, 0)", 
                           (canal_id, message.chat.id, enlace_invitacion, fecha_creacion))
            conn.commit()
        
        # Responder al usuario con un solo mensaje
        respuesta = f"{descripcion}\n{enlace_invitacion}"
        bot.send_message(message.chat.id, respuesta)
    except Exception as e:
        bot.send_message(message.chat.id, f"Error al generar el enlace: {e}")

# Comando /generar_enlace: permite a los usuarios generar un enlace de invitación de manera interactiva
@bot.message_handler(commands=['generar_enlace'])
def generar_enlace(message):
    if usuario_autenticado(message.chat.id):
        solicitar_enlace_canal(message)
    else:
        bot.send_message(message.chat.id, "Debes estar registrado y logueado para usar este comando.")

# Función para manejar los clics en el enlace y los nuevos seguidores
@bot.message_handler(func=lambda message: True, content_types=['new_chat_members', 'left_chat_member'])
def manejar_nuevos_seguidores(message):
    if message.content_type == 'new_chat_members':
        for new_member in message.new_chat_members:
            with sqlite3.connect('telegram_bot.db') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT canal_id FROM suscripciones WHERE chat_id = ?", (message.chat.id,))
                canal_id = cursor.fetchone()[0]
                actualizar_nuevos_seguidores(canal_id)
                cursor.execute("INSERT INTO suscripciones (chat_id, canal_id, fecha_suscripcion) VALUES (?, ?, ?)", 
                               (new_member.id, canal_id, datetime.now()))
                conn.commit()
    elif message.content_type == 'left_chat_member':
        with sqlite3.connect('telegram_bot.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT canal_id FROM suscripciones WHERE chat_id = ?", (message.chat.id,))
            canal_id = cursor.fetchone()[0]
            actualizar_nuevos_seguidores(canal_id)

# Función para manejar los clics en los enlaces
@app.route('/click/<enlace_id>')
def manejar_clicks_enlace(enlace_id):
    with sqlite3.connect('telegram_bot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT enlace, canal_id FROM enlaces WHERE id = ?", (enlace_id,))
        enlace_info = cursor.fetchone()
        if enlace_info:
            enlace, canal_id = enlace_info
            cursor.execute("UPDATE enlaces SET clicks_recibidos = clicks_recibidos + 1 WHERE id = ?", (enlace_id,))
            cursor.execute("UPDATE canales SET clicks = clicks + 1 WHERE id = ?", (canal_id,))
            conn.commit()
            actualizar_nuevos_seguidores(canal_id)
            return redirect(enlace)
        else:
            return "Enlace no encontrado", 404

# Función para actualizar las estadísticas automáticamente cada 1 minuto
def actualizar_estadisticas():
    while True:
        with sqlite3.connect('telegram_bot.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM canales")
            canales = cursor.fetchall()
            for canal in canales:
                actualizar_nuevos_seguidores(canal[0])
        time.sleep(60)  # Esperar 1 minuto

# Función para enviar el reporte diario automáticamente a las 00:00 hs de Argentina
def programar_reporte_diario():
    while True:
        now = datetime.now(pytz.timezone('America/Argentina/Buenos_Aires'))
        next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_time = (next_run - now).total_seconds()
        time.sleep(sleep_time)
        
        with sqlite3.connect('telegram_bot.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM usuarios")
            usuarios = cursor.fetchall()
            for usuario in usuarios:
                enviar_reporte_diario(usuario[0])

# Iniciar el bot y programar el primer reporte diario
if __name__ == "__main__":
    crear_tablas()
    threading.Thread(target=actualizar_estadisticas).start()
    threading.Thread(target=programar_reporte_diario).start()
    threading.Thread(target=lambda: app.run(port=5000)).start()
    bot.polling(none_stop=True)

