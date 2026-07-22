import os
import json
import requests
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")
NOMBRE_NEGOCIO = "Marquesas Orangel"

def send_telegram(chat_id, text, photo=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if photo:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        data = {"chat_id": chat_id, "caption": text, "parse_mode": "Markdown", "photo": photo}
    requests.post(url, data=data)

def send_whatsapp(mensaje):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        return
    url = f"https://api.callmebot.com/whatsapp.php?phone={MI_NUMERO_WHATSAPP}&text={mensaje}&apikey={CALLMEBOT_API_KEY}"
    requests.get(url)

def main():
    with open("catalog.json", "r") as f:
        catalog = json.load(f)
    
    day = datetime.now().day
    index = (day - 1) % len(catalog)
    product = catalog[index]
    
    mensaje = (
        f"🍰 *Promoción del día de {NOMBRE_NEGOCIO}*\n\n"
        f"Hoy destacamos: *{product['nombre']}* ({product['gramos']})\n"
        f"💰 Precio: {product['precio']}\n"
        f"📍 Retiro en Oropeza Castillo.\n\n"
        f"📲 ¡Pídelo ya! Escribe /menu en nuestro bot de Telegram."
    )
    
    if CHANNEL_ID:
        send_telegram(CHANNEL_ID, mensaje, product.get("imagen"))
        print("Promo enviada a Telegram")
    
    if CALLMEBOT_API_KEY and MI_NUMERO_WHATSAPP:
        msg_whatsapp = f"🍰 Promoción: {product['nombre']} {product['gramos']} - {product['precio']} - Retiro Oropeza Castillo."
        send_whatsapp(msg_whatsapp)
        print("Promo enviada a WhatsApp")

if __name__ == "__main__":
    main()
