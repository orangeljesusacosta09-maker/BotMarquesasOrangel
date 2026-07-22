import os
import json
import logging
import requests

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")

DIRECCION = "Oropeza Castillo, [Pon aquí tu calle y número]"
NOMBRE_NEGOCIO = "Marquesas Orangel"

OFFSET_FILE = "offset.json"
ORDERS_FILE = "orders.json"

def load_catalog():
    with open("catalog.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_offset():
    try:
        with open(OFFSET_FILE, "r") as f:
            return json.load(f).get("offset", 0)
    except:
        return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)

def load_orders():
    try:
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_orders(orders):
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)

def send_telegram(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=data)
    except Exception as e:
        logging.error(f"Error enviando mensaje: {e}")

# --- NUEVA FUNCIÓN PARA ENVIAR FOTOS ---
def send_photo_telegram(chat_id, photo_path, caption, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    try:
        # Abrimos el archivo de la foto desde el repositorio
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': parse_mode}
            requests.post(url, files=files, data=data)
    except Exception as e:
        logging.error(f"Error enviando foto: {e}")
        # Si falla la foto, enviamos solo el texto
        send_telegram(chat_id, caption)

def send_whatsapp_alert(mensaje):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        return
    url = f"https://api.callmebot.com/whatsapp.php?phone={MI_NUMERO_WHATSAPP}&text={mensaje}&apikey={CALLMEBOT_API_KEY}"
    try:
        requests.get(url)
    except Exception as e:
        logging.error(f"Error enviando WhatsApp: {e}")

def process_message(update):
    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    user_id = str(message["from"]["id"])

    if text == "/start":
        send_telegram(chat_id,
            f"🍰 ¡Bienvenido a {NOMBRE_NEGOCIO}!\n\n"
            "Envía /menu para ver el catálogo.\n"
            f"📍 Retiro en {DIRECCION}."
        )
        return

    if text == "/menu":
        catalog = load_catalog()
        msg = "📋 *Nuestro Menú:*\n\n"
        for i, item in enumerate(catalog, start=1):
            msg += f"{i}. {item['nombre']} - {item['gramos']} ({item['precio']})\n"
        msg += "\nResponde con el *número* que deseas."
        send_telegram(chat_id, msg)
        return

    if text.isdigit():
        num = int(text)
        catalog = load_catalog()
        if 1 <= num <= len(catalog):
            product = catalog[num-1]
            orders = load_orders()
            if user_id not in orders:
                orders[user_id] = {}
            orders[user_id]["producto"] = f"{product['nombre']} - {product['gramos']} ({product['precio']})"
            orders[user_id]["estado"] = "esperando_telefono"
            save_orders(orders)

            # --- AQUÍ ENVÍA LA FOTO ---
            caption = (f"✅ *Elegiste:* {product['nombre']} ({product['gramos']})\n"
                       f"💰 *Precio:* {product['precio']}\n\n"
                       "📱 Ahora envíame *tu número de WhatsApp* (ej: 0414-1234567).")
            send_photo_telegram(chat_id, product['imagen'], caption)
        else:
            send_telegram(chat_id, "❌ Número inválido. Usa /menu.")
        return

    orders = load_orders()
    if user_id in orders and orders[user_id].get("estado") == "esperando_telefono":
        phone = text
        orders[user_id]["telefono"] = phone
        orders[user_id]["estado"] = "completado"
        producto = orders[user_id]["producto"]
        save_orders(orders)

        send_telegram(chat_id,
            f"🎉 ¡Pedido listo!\nProducto: {producto}\nTeléfono: {phone}\n📍 Retiro: {DIRECCION}\n\nPronto te contactaré."
        )

        alerta = f"¡NUEVO+PEDIDO!%0AProducto: {producto}%0ATeléfono: {phone}%0ACliente: @{message['from'].get('username', 'sin usuario')}"
        send_whatsapp_alert(alerta)
        return

    send_telegram(chat_id, "📌 Usa /menu para ver los productos.")

def main():
    offset = load_offset()
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 30}
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        if data.get("ok"):
            for result in data.get("result", []):
                process_message(result)
                if result["update_id"] >= offset:
                    offset = result["update_id"] + 1
            save_offset(offset)
        else:
            logging.error(f"Error: {data}")
    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()
