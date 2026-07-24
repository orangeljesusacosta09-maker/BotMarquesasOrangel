import os
import json
import logging
import requests
import re
from flask import Flask, request, jsonify
from urllib.parse import quote
from datetime import datetime, timedelta

# ============================
# CONFIGURACIÓN
# ============================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")

SECRET_KEY = os.environ.get("SECRET_KEY", "clave_por_defecto_cambiala")
GOOGLE_SHEETS_URL = "https://script.google.com/macros/s/AKfycbyEoRuA-EhaaRQdFB6VABTj6WfuApkBi_4YKTUMF5OTQPvn8IglLRCzFdYTC9Td8Wl1Xw/exec"

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
        return {}
    except json.JSONDecodeError:
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

def send_photo_telegram(chat_id, photo_path, caption, parse_mode="Markdown"):
    try:
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

def send_whatsapp_alert(producto, telefono, cliente, tipo_pago, metodo_pago, fecha_vencimiento=None):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        return
    numero_limpio = MI_NUMERO_WHATSAPP.replace(" ", "").replace("-", "").replace("+", "")
    if not numero_limpio.isdigit():
        return

    if tipo_pago == "Crédito" and fecha_vencimiento:
        mensaje_texto = f"Nuevo pedido. Producto: {producto[:30]}. Tel: {telefono}. Cliente: {cliente}. Tipo: CREDITO ({metodo_pago}). Vence: {fecha_vencimiento}"
    else:
        mensaje_texto = f"Nuevo pedido. Producto: {producto[:30]}. Tel: {telefono}. Cliente: {cliente}. Tipo: CONTADO ({metodo_pago})"

    mensaje_codificado = quote(mensaje_texto, safe='')
    url = f"https://api.callmebot.com/whatsapp.php?phone={numero_limpio}&text={mensaje_codificado}&apikey={CALLMEBOT_API_KEY}"

    logging.info(f"📤 URL WHATSAPP: {url}")
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and ("queued" in resp.text.lower() or "success" in resp.text.lower()):
            logging.info("✅ Mensaje encolado correctamente")
        else:
            logging.warning(f"⚠️ Respuesta inesperada: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Error: {e}")

def registrar_venta_en_sheets(producto, precio, telefono, cliente, tipo_pago, metodo_pago, fecha_vencimiento=None):
    try:
        data = {
            "producto": producto,
            "precio": precio,
            "telefono": telefono,
            "cliente": cliente,
            "estado": "Completado",
            "tipo_pago": tipo_pago,
            "fecha_vencimiento": fecha_vencimiento if fecha_vencimiento else "",
            "metodo_pago": metodo_pago,
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
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    user_id = str(message["from"]["id"])
    username = message["from"].get("username", "sin_username")
    first_name = message["from"].get("first_name", "cliente")

    logging.info(f"📩 Mensaje de {username} (ID:{user_id}): '{text}'")

    orders = load_orders()
    user_order = orders.get(user_id, {})

    # ============================================
    # 1. CAPTURA DE TELÉFONO
    # ============================================
    if user_order.get("estado") == "esperando_telefono":
        phone = text
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            send_telegram(chat_id, "📱 Por favor, envía un número de WhatsApp válido (ej: 0412-1234567).")
            return

        orders[user_id]["telefono"] = phone
        orders[user_id]["estado"] = "esperando_pago"
        save_orders(orders)

        send_telegram(chat_id,
            f"✅ Teléfono guardado: {phone}\n\n"
            "💰 Ahora elige la forma de pago:\n"
            "1️⃣ Contado\n"
            "2️⃣ Crédito (máximo 7 días)\n\n"
            "Responde con el *número* (1 o 2)."
        )
        return

    # ============================================
    # 2. CAPTURA DE FORMA DE PAGO (CONTADO/CRÉDITO)
    # ============================================
    if user_order.get("estado") == "esperando_pago":
        if text == "1":
            orders[user_id]["tipo_pago"] = "Contado"
            orders[user_id]["estado"] = "esperando_metodo_pago"
            save_orders(orders)
            send_telegram(chat_id,
                "💳 Ahora elige el *método de pago*:\n\n"
                "1️⃣ Binance\n"
                "2️⃣ Zinli\n"
                "3️⃣ Banesco\n"
                "4️⃣ Venezuela (Pago Móvil)\n\n"
                "Responde con el *número* (1, 2, 3 o 4)."
            )
            return

        elif text == "2":
            orders[user_id]["tipo_pago"] = "Crédito"
            orders[user_id]["estado"] = "esperando_dias_credito"
            save_orders(orders)
            send_telegram(chat_id,
                "📅 Has elegido **Crédito**.\n"
                "¿En cuántos días cancelas? (máximo 7 días)\n\n"
                "Responde con un número del *1 al 7*."
            )
            return

        else:
            send_telegram(chat_id, "❌ Opción inválida. Responde *1* para Contado o *2* para Crédito.")
            return

    # ============================================
    # 3. CAPTURA DE DÍAS DE CRÉDITO
    # ============================================
    if user_order.get("estado") == "esperando_dias_credito":
        if text.isdigit():
            dias = int(text)
            if 1 <= dias <= 7:
                orders[user_id]["dias_credito"] = dias
                orders[user_id]["estado"] = "esperando_metodo_pago"
                save_orders(orders)
                send_telegram(chat_id,
                    "💳 Ahora elige el *método de pago*:\n\n"
                    "1️⃣ Binance\n"
                    "2️⃣ Zinli\n"
                    "3️⃣ Banesco\n"
                    "4️⃣ Venezuela (Pago Móvil)\n\n"
                    "Responde con el *número* (1, 2, 3 o 4)."
                )
                return
            else:
                send_telegram(chat_id, "❌ El número debe ser entre *1 y 7*. Por favor, elige un número válido.")
                return
        else:
            send_telegram(chat_id, "❌ Por favor, responde con un número del *1 al 7*.")
            return

    # ============================================
    # 4. CAPTURA DE MÉTODO DE PAGO
    # ============================================
    if user_order.get("estado") == "esperando_metodo_pago":
        metodos = {
            "1": "Binance",
            "2": "Zinli",
            "3": "Banesco",
            "4": "Venezuela (Pago Móvil)"
        }
        if text in metodos:
            metodo_pago = metodos[text]
            producto = user_order.get("producto", "")
            telefono = user_order.get("telefono", "")
            tipo_pago = user_order.get("tipo_pago", "Contado")
            precio = re.search(r'\(([^)]+)\)', producto)
            precio = precio.group(1) if precio else "N/A"

            if tipo_pago == "Crédito":
                dias = user_order.get("dias_credito", 7)
                fecha_actual = datetime.now()
                fecha_vencimiento = fecha_actual + timedelta(days=dias)
                fecha_vencimiento_str = fecha_vencimiento.strftime("%d/%m/%Y")
                registrar_venta_en_sheets(producto, precio, telefono, username, tipo_pago, metodo_pago, fecha_vencimiento_str)
                
                # Mensaje al cliente
                send_telegram(chat_id,
                    f"✅ ¡Gracias, {first_name}!\n\n"
                    "Tu pedido ha sido registrado como **Crédito**.\n"
                    f"📅 Fecha de vencimiento: *{fecha_vencimiento_str}*\n"
                    f"💰 Método de pago: *{metodo_pago}*\n\n"
                    "En los próximos minutos te contactaré para coordinar la entrega.\n\n"
                    f"🚚 *Delivery en {DIRECCION}*\n🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
                )
                
                # 🔥 ALERTA AL DUEÑO POR TELEGRAM (¡AHORA SÍ!)
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {telefono}\nCliente: @{username}\nTipo: {tipo_pago} ({metodo_pago})\nVence: {fecha_vencimiento_str}"
                )
                
                # Alerta WhatsApp
                send_whatsapp_alert(producto, telefono, username, tipo_pago, metodo_pago, fecha_vencimiento_str)
                
            else:  # Contado
                registrar_venta_en_sheets(producto, precio, telefono, username, tipo_pago, metodo_pago, None)
                
                # Mensaje al cliente
                send_telegram(chat_id,
                    f"✅ ¡Gracias, {first_name}!\n\n"
                    "Tu pedido ha sido registrado como **Contado**.\n"
                    f"💰 Método de pago: *{metodo_pago}*\n\n"
                    "En los próximos minutos te contactaré para coordinar la entrega.\n\n"
                    f"🚚 *Delivery en {DIRECCION}*\n🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
                )
                
                # 🔥 ALERTA AL DUEÑO POR TELEGRAM
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {telefono}\nCliente: @{username}\nTipo: {tipo_pago} ({metodo_pago})"
                )
                
                # Alerta WhatsApp
                send_whatsapp_alert(producto, telefono, username, tipo_pago, metodo_pago, None)

            # Limpiar estado del usuario
            del orders[user_id]
            save_orders(orders)
            return
        else:
            send_telegram(chat_id, "❌ Opción inválida. Responde con el *número* del método de pago.")
            return

    # ============================================
    # 5. COMANDOS /start y /menu
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
    # 6. SELECCIÓN DE PRODUCTO
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
