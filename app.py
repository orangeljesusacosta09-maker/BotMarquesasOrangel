import os
import json
import logging
import requests
from flask import Flask, request, jsonify

# ============================
# CONFIGURACIÓN
# ============================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")

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
    except:
        return {}

def save_orders(orders):
    try:
        with open(ORDERS_FILE, "w") as f:
            json.dump(orders, f, indent=2)
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

def send_photo_telegram(chat_id, photo_path, caption, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': parse_mode}
            resp = requests.post(url, files=files, data=data)
            if resp.status_code != 200:
                logging.error(f"Error enviando foto: {resp.text}")
            else:
                logging.info(f"Foto enviada a {chat_id}")
    except Exception as e:
        logging.error(f"Excepción enviando foto: {e}")
        send_telegram(chat_id, caption)

def send_whatsapp_alert(mensaje):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        logging.warning("Faltan credenciales de WhatsApp")
        return
    url = f"https://api.callmebot.com/whatsapp.php?phone={MI_NUMERO_WHATSAPP}&text={mensaje}&apikey={CALLMEBOT_API_KEY}"
    try:
        requests.get(url)
        logging.info("Alerta WhatsApp enviada")
    except Exception as e:
        logging.error(f"Error enviando WhatsApp: {e}")

# ============================
# PROCESAMIENTO DE MENSAJES (CORREGIDO)
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

    # ============================================
    # 1. CAPTURA DE TELÉFONO (PRIORIDAD MÁXIMA)
    # ============================================
    orders = load_orders()
    if user_id in orders and orders[user_id].get("estado") == "esperando_telefono":
        # Cualquier mensaje que envíe el usuario aquí es su número de teléfono
        phone = text
        # Limpiar el teléfono de caracteres no numéricos (opcional)
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        # Validación básica: al menos 10 dígitos (para evitar respuestas vacías)
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            send_telegram(chat_id, "📱 Por favor, envía un número de WhatsApp válido (ej: 0412-1234567).")
            return
        # Guardar pedido completado
        orders[user_id]["telefono"] = phone
        orders[user_id]["estado"] = "completado"
        producto = orders[user_id]["producto"]
        save_orders(orders)

        send_telegram(chat_id,
            f"✅ ¡Gracias, {first_name}!\n\n"
            "Tu pedido ha sido recibido. En los próximos minutos te contactaré para coordinar el pago y la entrega.\n\n"
            f"🚚 *Delivery en {DIRECCION}*\n🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
        )

        # Alerta al dueño (WhatsApp + Telegram)
        alerta = f"¡NUEVO+PEDIDO!%0AProducto: {producto}%0ATeléfono: {phone}%0ACliente: @{username}"
        send_whatsapp_alert(alerta)
        
        if CHAT_ID_DUENO:
            try:
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {phone}\nCliente: @{username}"
                )
            except Exception as e:
                logging.error(f"Error enviando alerta al dueño: {e}")
        return

    # ============================================
    # 2. COMANDOS /start y /menu
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
    # 3. SELECCIÓN DE PRODUCTO (número del menú)
    # ============================================
    if text.isdigit():
        num = int(text)
        catalog = load_catalog()
        if 1 <= num <= len(catalog):
            product = catalog[num-1]
            # Guardar estado del pedido
            orders = load_orders()
            if user_id not in orders:
                orders[user_id] = {}
            orders[user_id]["producto"] = f"{product['nombre']} - {product['gramos']} ({product['precio']})"
            orders[user_id]["estado"] = "esperando_telefono"
            save_orders(orders)

            caption = (f"✅ *Elegiste:* {product['nombre']} ({product['gramos']})\n"
                       f"💰 *Precio:* {product['precio']}\n\n"
                       f"🚚 *Delivery:* {DIRECCION} (sin costo extra)\n"
                       "📱 Ahora envíame *tu número de WhatsApp* (ej: 0412-1234567).")
            # Enviar foto si existe
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
