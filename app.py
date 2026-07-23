import os
import json
import logging
import requests
import re
from flask import Flask, request, jsonify
from urllib.parse import quote

# ============================
# CONFIGURACIÓN
# ============================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")

# 🔐 CLAVE SECRETA (DEBE COINCIDIR CON LA DE APPS SCRIPT)
SECRET_KEY = os.environ.get("SECRET_KEY", "clave_por_defecto_cambiala")

# ✅ URL CORRECTA DE GOOGLE SHEETS (LA QUE ME DISTE)
GOOGLE_SHEETS_URL = "https://script.google.com/macros/s/AKfycbyQ5t7zqo1TjOwchsXdjfYSzWF8-IkcslWUArwhKcda2ib0vI5H4aflxPzmmdw6eVXGfw/exec"
DIRECCION = "Oropeza Castillo"
NOMBRE_NEGOCIO = "Marquesas Orangel"
ORDERS_FILE = "orders.json"

# ============================
# FUNCIONES AUXILIARES
# ============================
def load_catalog():
    try:
        with open("catalog.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error cargando catalog.json: {e}")
        return []

def load_orders():
    try:
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning("orders.json no encontrado, se creará uno nuevo")
        return {}
    except json.JSONDecodeError:
        logging.error("orders.json corrupto, se reiniciará")
        return {}

def save_orders(orders):
    try:
        with open(ORDERS_FILE, "w") as f:
            json.dump(orders, f, indent=2)
        logging.info("✅ orders.json guardado correctamente")
    except Exception as e:
        logging.error(f"Error guardando orders.json: {e}")

def send_telegram(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        resp = requests.post(url, json=data)
        if resp.status_code != 200:
            logging.error(f"Error enviando mensaje: {resp.text}")
        else:
            logging.info(f"Mensaje enviado a {chat_id}")
    except Exception as e:
        logging.error(f"Excepción enviando mensaje: {e}")

# ============================
# FUNCIÓN PARA ENVIAR FOTO CON MANEJO DE ERRORES (CORREGIDA)
# ============================
def send_photo_telegram(chat_id, photo_path, caption, parse_mode="Markdown"):
    try:
        # Verificar si el archivo existe antes de intentar enviarlo
        if not os.path.exists(photo_path):
            logging.warning(f"⚠️ Foto no encontrada: {photo_path}. Enviando solo texto.")
            send_telegram(chat_id, caption)
            return

        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': parse_mode}
            resp = requests.post(url, files=files, data=data)
            if resp.status_code != 200:
                logging.error(f"Error enviando foto: {resp.text}")
                send_telegram(chat_id, caption)
            else:
                logging.info(f"Foto enviada a {chat_id}")
    except Exception as e:
        logging.error(f"Excepción enviando foto: {e}")
        send_telegram(chat_id, caption)

# ============================
# FUNCIÓN WHATSAPP (MENSAJE CORTO)
# ============================
def send_whatsapp_alert(producto, telefono, cliente):
    if not CALLMEBOT_API_KEY:
        logging.error("❌ CALLMEBOT_API_KEY no está definida")
        return
    if not MI_NUMERO_WHATSAPP:
        logging.error("❌ MI_NUMERO_WHATSAPP no está definida")
        return

    numero_limpio = MI_NUMERO_WHATSAPP.replace(" ", "").replace("-", "").replace("+", "")
    if not numero_limpio.isdigit():
        logging.error(f"❌ Número inválido: {numero_limpio}")
        return

    producto_corto = producto[:30]
    mensaje_texto = f"Nuevo pedido. Producto: {producto_corto}. Tel: {telefono}. Cliente: {cliente}"
    mensaje_codificado = quote(mensaje_texto, safe='')
    url = f"https://api.callmebot.com/whatsapp.php?phone={numero_limpio}&text={mensaje_codificado}&apikey={CALLMEBOT_API_KEY}"

    logging.info(f"📤 URL WHATSAPP: {url}")
    try:
        resp = requests.get(url, timeout=30)
        logging.info(f"✅ Código HTTP: {resp.status_code}")
        logging.info(f"📄 Respuesta: {resp.text[:200]}")
        if resp.status_code == 200 and ("queued" in resp.text.lower() or "success" in resp.text.lower()):
            logging.info("✅ Mensaje encolado correctamente (llegará en 1-2 min)")
        else:
            logging.warning(f"⚠️ Respuesta inesperada: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Error: {e}")

# ============================
# FUNCIÓN PARA REGISTRAR EN GOOGLE SHEETS (CON LA URL CORRECTA)
# ============================
def registrar_venta_en_sheets(producto, telefono, cliente):
    try:
        precio_match = re.search(r'\(([^)]+)\)', producto)
        precio = precio_match.group(1) if precio_match else "N/A"
        
        data = {
            "producto": producto,
            "precio": precio,
            "telefono": telefono,
            "cliente": cliente,
            "estado": "Completado",
            "secret": SECRET_KEY
        }
        resp = requests.post(GOOGLE_SHEETS_URL, json=data, timeout=10)
        if resp.status_code == 200:
            logging.info("✅ Venta registrada en Google Sheets")
        else:
            logging.error(f"❌ Error registrando en Sheets: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Excepción al registrar en Sheets: {e}")

# ============================
# PROCESAMIENTO DE MENSAJES
# ============================
def process_message(update):
    message = update.get("message")
    if not message:
        logging.warning("Mensaje sin campo 'message'")
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    user_id = str(message["from"]["id"])
    username = message["from"].get("username", "sin_username")
    first_name = message["from"].get("first_name", "cliente")

    logging.info(f"📩 Mensaje de {username} (ID:{user_id}): '{text}'")

    orders = load_orders()
    logging.info(f"📋 orders actual: {orders}")

    # ============================================
    # 1. CAPTURA DE TELÉFONO
    # ============================================
    user_order = orders.get(user_id)
    if user_order and user_order.get("estado") == "esperando_telefono":
        phone = text
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            send_telegram(chat_id, "📱 Por favor, envía un número de WhatsApp válido (ej: 0412-1234567).")
            return

        orders[user_id]["telefono"] = phone
        orders[user_id]["estado"] = "completado"
        producto = orders[user_id]["producto"]
        save_orders(orders)

        # 🔥 REGISTRAR VENTA EN GOOGLE SHEETS
        registrar_venta_en_sheets(producto, phone, username)

        # Mensaje al cliente
        send_telegram(chat_id,
            f"✅ ¡Gracias, {first_name}!\n\n"
            "Tu pedido ha sido recibido y está en proceso.\n"
            "En los próximos **1 o 2 minutos** recibirás un mensaje de confirmación en tu WhatsApp.\n"
            "Por favor, **espera** y no envíes más mensajes mientras se procesa.\n\n"
            f"🚚 *Delivery en {DIRECCION}*\n"
            f"🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
        )

        # --- ALERTA AL DUEÑO (WhatsApp) ---
        send_whatsapp_alert(producto, phone, username)

        # --- ALERTA AL DUEÑO (Telegram) ---
        if CHAT_ID_DUENO:
            try:
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {phone}\nCliente: @{username}"
                )
            except Exception as e:
                logging.error(f"Error enviando alerta al dueño: {e}")
        return

    # ============================================
    # 2. COMANDOS
    # ============================================
    if text == "/start":
        send_telegram(chat_id,
            f"🍰 ¡Bienvenido a {NOMBRE_NEGOCIO}!\n\n"
            "Envía /menu para ver el catálogo.\n"
            f"🚚 *Delivery:* Disponible SOLO en {DIRECCION}."
        )
        return

    if text == "/menu":
        catalog = load_catalog()
        if not catalog:
            send_telegram(chat_id, "❌ Error al cargar el catálogo. Contacta al administrador.")
            return
        msg = "📋 *Nuestro Menú:*\n\n"
        for i, item in enumerate(catalog, start=1):
            msg += f"{i}. {item['nombre']} - {item['gramos']} ({item['precio']})\n"
        msg += f"\nResponde con el *número* que deseas.\n\n🚚 *Delivery en {DIRECCION}.*"
        send_telegram(chat_id, msg)
        return

    # ============================================
    # 3. SELECCIÓN DE PRODUCTO
    # ============================================
    if text.isdigit():
        num = int(text)
        catalog = load_catalog()
        if 1 <= num <= len(catalog):
            product = catalog[num-1]
            if user_id not in orders:
                orders[user_id] = {}
            orders[user_id]["producto"] = f"{product['nombre']} - {product['gramos']} ({product['precio']})"
            orders[user_id]["estado"] = "esperando_telefono"
            save_orders(orders)
            logging.info(f"✅ Estado guardado para {user_id}: {orders[user_id]}")

            caption = (f"✅ *Elegiste:* {product['nombre']} ({product['gramos']})\n"
                       f"💰 *Precio:* {product['precio']}\n\n"
                       f"🚚 *Delivery:* {DIRECCION} (sin costo extra)\n"
                       "📱 Ahora envíame *tu número de WhatsApp* (ej: 0412-1234567).")
            try:
                send_photo_telegram(chat_id, product['imagen'], caption)
            except Exception as e:
                logging.error(f"Error enviando foto: {e}")
                send_telegram(chat_id, caption)
        else:
            send_telegram(chat_id, "❌ Número inválido. Usa /menu.")
        return

    # ============================================
    # 4. MENSAJE POR DEFECTO
    # ============================================
    send_telegram(chat_id, "📌 Usa /menu para ver los productos.")

# ============================
# RUTAS DE FLASK
# ============================
@app.route('/', methods=['GET'])
def index():
    return "🍰 Bot de Marquesas está vivo!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if update and "message" in update:
            logging.info("Webhook recibido, procesando mensaje...")
            process_message(update)
        else:
            logging.warning("Webhook recibido sin mensaje")
        return "ok", 200
    except Exception as e:
        logging.error(f"Error en webhook: {e}")
        return "error", 500

@app.route('/setup', methods=['GET'])
def setup():
    base_url = request.host_url.rstrip('/')
    webhook_url = f"{base_url}/webhook"
    set_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    try:
        resp = requests.get(set_url)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)})

# ============================
# ENTRADA PRINCIPAL
# ============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
