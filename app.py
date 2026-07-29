import os
import json
import logging
import requests
import re
from flask import Flask, request, jsonify
from urllib.parse import quote
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")
SECRET_KEY = os.environ.get("SECRET_KEY", "Marquesas2026!Segura")
GOOGLE_SHEETS_URL = os.environ.get("GOOGLE_SHEETS_URL", "https://script.google.com/macros/s/AKfycbyKCqMEcaATBCk8EfEMjMtoaE_Fb502l4P2G-CIe54RaULXADzCUPlE1CFKI0mXumE00A/exec")

DIRECCION = "Oropeza Castillo"
NOMBRE_NEGOCIO = "Marquesas Orangel"

# ============================
# ESTADO EN MEMORIA
# ============================
SESSION_CACHE = {}

def get_user_state(user_id):
    return SESSION_CACHE.get(user_id, {})

def set_user_state(user_id, data):
    SESSION_CACHE[user_id] = data
    logging.info(f"📦 Estado actualizado para {user_id}: {data}")

def clear_user_state(user_id):
    if user_id in SESSION_CACHE:
        del SESSION_CACHE[user_id]
        logging.info(f"🗑️ Estado eliminado para {user_id}")

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

def send_album_telegram(chat_id, catalog):
    try:
        media_group = []
        files = {}
        for i, item in enumerate(catalog):
            if not os.path.exists(item['imagen']):
                logging.warning(f"Imagen no encontrada: {item['imagen']}")
                continue
            file_key = f"photo_{i}"
            files[file_key] = open(item['imagen'], 'rb')
            caption = f"{item['nombre']} - {item['gramos']}\n💰 {item['precio']}"
            media_group.append({
                "type": "photo",
                "media": f"attach://{file_key}",
                "caption": caption,
                "parse_mode": "Markdown"
            })
            if len(media_group) == 10:
                break
        if not media_group:
            return False
        url = f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup"
        data = {"chat_id": chat_id, "media": json.dumps(media_group)}
        resp = requests.post(url, data=data, files=files)
        if resp.status_code != 200:
            logging.error(f"Error enviando álbum: {resp.text}")
            return False
        logging.info(f"📸 Álbum enviado con {len(media_group)} fotos")
        return True
    except Exception as e:
        logging.error(f"Excepción enviando álbum: {e}")
        return False

# 🔥 FUNCIÓN WHATSAPP OPTIMIZADA (MENSAJE CORTO Y SIN EMOJIS)
def send_whatsapp_alert(producto, telefono, cliente, tipo_pago, metodo_pago, fecha_vencimiento=None):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        return
    numero_limpio = MI_NUMERO_WHATSAPP.replace(" ", "").replace("-", "").replace("+", "")
    if not numero_limpio.isdigit():
        return

    # Limpiar producto: eliminar emojis y caracteres raros
    producto_corto = producto[:30]
    producto_corto = producto_corto.encode('ascii', 'ignore').decode('ascii')
    if tipo_pago == "Crédito" and fecha_vencimiento:
        mensaje_texto = f"Nuevo pedido. Producto: {producto_corto}. Tel: {telefono}. Cliente: {cliente}. Tipo: CREDITO ({metodo_pago}). Vence: {fecha_vencimiento}"
    else:
        mensaje_texto = f"Nuevo pedido. Producto: {producto_corto}. Tel: {telefono}. Cliente: {cliente}. Tipo: CONTADO ({metodo_pago})"

    mensaje_codificado = quote(mensaje_texto, safe='')
    url = f"https://api.callmebot.com/whatsapp.php?phone={numero_limpio}&text={mensaje_codificado}&apikey={CALLMEBOT_API_KEY}"

    logging.info(f"📤 URL WHATSAPP (optimizada): {url[:100]}...")
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and ("queued" in resp.text.lower() or "success" in resp.text.lower()):
            logging.info("✅ Mensaje encolado correctamente")
        else:
            logging.warning(f"⚠️ Respuesta inesperada: {resp.text[:200]}")
    except Exception as e:
        logging.error(f"❌ Error: {e}")

# 🔥 REGISTRO EN SHEETS CON EXTRACCIÓN CORRECTA DE PRECIO
def registrar_venta_en_sheets(producto, telefono, cliente, tipo_pago, metodo_pago, fecha_vencimiento=None):
    try:
        # 🔥 Extraer precio: SIEMPRE el último paréntesis
        precio_match = re.search(r'\(([^)]+)\)\s*$', producto)
        precio = precio_match.group(1) if precio_match else "N/A"

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
            logging.info("✅ Venta registrada en Google Sheets (VentasBot)")
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

    # ============================================
    # COMANDOS (SIEMPRE PRIORITARIOS)
    # ============================================
    if text == "/start":
        clear_user_state(user_id)
        send_telegram(chat_id,
            f"🍰 ¡Bienvenido a {NOMBRE_NEGOCIO}!\n\n"
            "Envía /menu para ver el catálogo.\n"
            f"🚚 *Delivery:* Disponible SOLO en {DIRECCION}."
        )
        return

    if text == "/menu":
        clear_user_state(user_id)
        catalog = load_catalog()
        if not catalog:
            send_telegram(chat_id, "❌ Error al cargar el catálogo. Contacta al administrador.")
            return

        send_album_telegram(chat_id, catalog)

        msg = "📋 *Nuestro Catálogo:*\n\n"
        for i, item in enumerate(catalog, start=1):
            msg += f"{i}. {item['nombre']} - {item['gramos']} ({item['precio']})\n"
        msg += f"\nResponde con el *número* que deseas.\n\n🚚 *Delivery en {DIRECCION}.*"
        send_telegram(chat_id, msg)
        return

    # ============================================
    # FLUJO DE COMPRA
    # ============================================
    state = get_user_state(user_id)
    estado_actual = state.get("estado")
    producto_actual = state.get("producto")
    telefono_actual = state.get("telefono")
    tipo_pago_actual = state.get("tipo_pago")
    dias_credito_actual = state.get("dias_credito")
    metodo_pago_actual = state.get("metodo_pago")

    logging.info(f"🔍 Estado actual del usuario {user_id}: {estado_actual}")

    # CAPTURA DE TELÉFONO
    if estado_actual == "esperando_telefono":
        phone = text
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not phone_clean.isdigit() or len(phone_clean) < 10:
            send_telegram(chat_id, "📱 Por favor, envía un número de WhatsApp válido (ej: 0412-1234567).")
            return

        state["telefono"] = phone
        state["estado"] = "esperando_pago"
        set_user_state(user_id, state)

        send_telegram(chat_id,
            f"✅ Teléfono guardado: {phone}\n\n"
            "💰 Ahora elige la forma de pago:\n"
            "1️⃣ Contado\n"
            "2️⃣ Crédito (máximo 7 días)\n\n"
            "Responde con el *número* (1 o 2)."
        )
        return

    # CAPTURA DE FORMA DE PAGO
    if estado_actual == "esperando_pago":
        if text == "1":
            state["tipo_pago"] = "Contado"
            state["estado"] = "esperando_metodo_pago"
            set_user_state(user_id, state)
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
            state["tipo_pago"] = "Crédito"
            state["estado"] = "esperando_dias_credito"
            set_user_state(user_id, state)
            send_telegram(chat_id,
                "📅 Has elegido **Crédito**.\n"
                "¿En cuántos días cancelas? (máximo 7 días)\n\n"
                "Responde con un número del *1 al 7*."
            )
            return
        else:
            send_telegram(chat_id, "❌ Opción inválida. Responde *1* para Contado o *2* para Crédito.")
            return

    # CAPTURA DE DÍAS DE CRÉDITO
    if estado_actual == "esperando_dias_credito":
        if text.isdigit():
            dias = int(text)
            if 1 <= dias <= 7:
                state["dias_credito"] = dias
                state["estado"] = "esperando_metodo_pago"
                set_user_state(user_id, state)
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

    # CAPTURA DE MÉTODO DE PAGO
    if estado_actual == "esperando_metodo_pago":
        metodos = {
            "1": "Binance",
            "2": "Zinli",
            "3": "Banesco",
            "4": "Venezuela (Pago Móvil)"
        }
        if text in metodos:
            metodo_pago = metodos[text]
            producto = producto_actual
            telefono = telefono_actual
            tipo_pago = tipo_pago_actual

            if tipo_pago == "Crédito":
                dias = int(dias_credito_actual or 7)
                fecha_actual = datetime.now()
                fecha_vencimiento = fecha_actual + timedelta(days=dias)
                fecha_vencimiento_str = fecha_vencimiento.strftime("%d/%m/%Y")

                registrar_venta_en_sheets(producto, telefono, username, tipo_pago, metodo_pago, fecha_vencimiento_str)

                send_telegram(chat_id,
                    f"✅ ¡Gracias, {first_name}!\n\n"
                    "Tu pedido ha sido registrado como **Crédito**.\n"
                    f"📅 Fecha de vencimiento: *{fecha_vencimiento_str}*\n"
                    f"💰 Método de pago: *{metodo_pago}*\n\n"
                    "En los próximos minutos te contactaré para coordinar la entrega.\n\n"
                    f"🚚 *Delivery en {DIRECCION}*\n🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
                )
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {telefono}\nCliente: @{username}\nTipo: {tipo_pago} ({metodo_pago})\nVence: {fecha_vencimiento_str}"
                )
                send_whatsapp_alert(producto, telefono, username, tipo_pago, metodo_pago, fecha_vencimiento_str)
            else:
                registrar_venta_en_sheets(producto, telefono, username, tipo_pago, metodo_pago, None)

                send_telegram(chat_id,
                    f"✅ ¡Gracias, {first_name}!\n\n"
                    "Tu pedido ha sido registrado como **Contado**.\n"
                    f"💰 Método de pago: *{metodo_pago}*\n\n"
                    "En los próximos minutos te contactaré para coordinar la entrega.\n\n"
                    f"🚚 *Delivery en {DIRECCION}*\n🙏 ¡Gracias por preferir {NOMBRE_NEGOCIO}!"
                )
                send_telegram(CHAT_ID_DUENO,
                    f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {telefono}\nCliente: @{username}\nTipo: {tipo_pago} ({metodo_pago})"
                )
                send_whatsapp_alert(producto, telefono, username, tipo_pago, metodo_pago, None)

            clear_user_state(user_id)
            return
        else:
            send_telegram(chat_id, "❌ Opción inválida. Responde con el *número* del método de pago.")
            return

    # SELECCIÓN DE PRODUCTO (por número)
    if text.isdigit():
        num = int(text)
        catalog = load_catalog()
        if 1 <= num <= len(catalog):
            product = catalog[num-1]
            producto = f"{product['nombre']} - {product['gramos']} ({product['precio']})"

            clear_user_state(user_id)
            set_user_state(user_id, {
                "producto": producto,
                "estado": "esperando_telefono"
            })
            logging.info(f"🔍 Estado guardado para {user_id}: esperando_telefono")

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
    return "✅ Bot está vivo!", 200

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
