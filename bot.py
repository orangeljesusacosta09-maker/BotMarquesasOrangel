import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests
import time
import sys

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_DUENO = os.environ.get("TELEGRAM_CHAT_ID_DUENO")
CALLMEBOT_API_KEY = os.environ.get("CALLMEBOT_API_KEY")
MI_NUMERO_WHATSAPP = os.environ.get("MI_NUMERO_WHATSAPP")
DIRECCION = "Oropeza Castillo, [Pon aquí tu calle y número de casa]"
NOMBRE_NEGOCIO = "Marquesas Orangel"

# --- LEER CATÁLOGO ---
def load_catalog():
    with open("catalog.json", "r", encoding="utf-8") as f:
        return json.load(f)

# --- LEER/GUARDAR PEDIDOS ---
def load_orders():
    try:
        with open("orders.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_orders(orders):
    with open("orders.json", "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)

# --- ENVIAR ALERTA A WHATSAPP (CallMeBot) ---
def send_whatsapp_alert(mensaje):
    if not CALLMEBOT_API_KEY or not MI_NUMERO_WHATSAPP:
        print("Faltan credenciales de CallMeBot")
        return
    url = f"https://api.callmebot.com/whatsapp.php?phone={MI_NUMERO_WHATSAPP}&text={mensaje}&apikey={CALLMEBOT_API_KEY}"
    try:
        requests.get(url)
        print("Alerta enviada a WhatsApp")
    except Exception as e:
        print(f"Error enviando WhatsApp: {e}")

# --- COMANDO /START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🍰 ¡Bienvenido a {NOMBRE_NEGOCIO}!\n\n"
        "Aquí puedes pedir tus marquesas favoritas.\n"
        "Envía /menu para ver el catálogo con precios y fotos.\n\n"
        "⚠️ *Importante:* El retiro es SOLO en Oropeza Castillo (sin delivery).",
        parse_mode="Markdown"
    )

# --- COMANDO /MENU ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    catalog = load_catalog()
    keyboard = []
    for item in catalog:
        btn = InlineKeyboardButton(
            f"{item['nombre']} - {item['gramos']} ({item['precio']})",
            callback_data=f"select_{item['id']}"
        )
        keyboard.append([btn])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📋 *Nuestro Menú:*\nElige el que más te antoje:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- CUANDO EL CLIENTE ELIGE UN PRODUCTO (BOTÓN) ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[1])
    catalog = load_catalog()
    product = next((p for p in catalog if p["id"] == product_id), None)
    
    if not product:
        await query.edit_message_text("❌ Producto no encontrado.")
        return

    orders = load_orders()
    user_id = str(update.effective_user.id)
    
    if user_id not in orders:
        orders[user_id] = {}
    
    orders[user_id]["producto"] = f"{product['nombre']} - {product['gramos']} ({product['precio']})"
    orders[user_id]["estado"] = "esperando_telefono"
    save_orders(orders)

    await query.edit_message_text(
        f"✅ ¡Excelente elección!\n\n"
        f"Has seleccionado: *{product['nombre']}* ({product['gramos']})\n"
        f"Precio: {product['precio']}\n\n"
        "📍 *Retiro:* Oropeza Castillo (sin delivery).\n"
        "📱 Para finalizar, envíame *tu número de WhatsApp* (ej: 0414-1234567) y te contactaré para coordinar el pago y la entrega.",
        parse_mode="Markdown"
    )

# --- RECIBIR EL NÚMERO DE TELÉFONO ---
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    phone = update.message.text
    orders = load_orders()

    if user_id not in orders or orders[user_id].get("estado") != "esperando_telefono":
        await update.message.reply_text("Primero elige un producto con /menu")
        return

    orders[user_id]["telefono"] = phone
    orders[user_id]["estado"] = "completado"
    producto = orders[user_id]["producto"]
    save_orders(orders)

    await update.message.reply_text(
        f"🎉 ¡Pedido listo!\n\n"
        f"Producto: {producto}\n"
        f"Teléfono: {phone}\n"
        f"📍 Retiro en: {DIRECCION}\n\n"
        f"Pronto te escribiré para confirmar el pago. ¡Gracias!"
    )

    alerta = f"¡NUEVO+PEDIDO!%0AProducto: {producto}%0ATeléfono: {phone}%0ACliente: @{update.effective_user.username or 'sin usuario'}"
    send_whatsapp_alert(alerta)
    
    if CHAT_ID_DUENO:
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID_DUENO,
                text=f"🛎️ NUEVO PEDIDO\n{producto}\nTeléfono: {phone}\nCliente: @{update.effective_user.username}"
            )
        except:
            pass

# --- CAPTURAR CUALQUIER OTRO TEXTO ---
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Usa /menu para ver los productos.\n"
        "Si ya elegiste, solo envíame tu número de teléfono."
    )

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_click, pattern="^select_"))
    app.add_handler(MessageHandler(filters.Regex(r'^\d'), handle_phone))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))
    
    print("Bot iniciado, escuchando por 30 segundos...")
    # ¡Esta es la clave! Solo corre por 30 segundos y luego termina
    app.run_polling(timeout=10, drop_pending_updates=True, allowed_updates=None, close_loop=False)
    
    # Forzar cierre después de 30 segundos
    time.sleep(30)
    print("Tiempo cumplido, cerrando...")
    app.stop()
    sys.exit(0)

if __name__ == "__main__":
    main()
