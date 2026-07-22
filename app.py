import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, json=data)

@app.route('/', methods=['GET'])
def index():
    return "Bot vivo", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        if text == "/start":
            send_telegram(chat_id, "¡Bot funcionando! Envía /menu")
        elif text == "/menu":
            send_telegram(chat_id, "Menú: 1. Marquesa de Chocolate - 140g (2.2 Bs)")
        else:
            send_telegram(chat_id, "Comando no reconocido. Usa /menu")
    return "ok", 200

@app.route('/setup', methods=['GET'])
def setup():
    base_url = request.host_url.rstrip('/')
    webhook_url = f"{base_url}/webhook"
    set_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    resp = requests.get(set_url)
    return jsonify(resp.json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
