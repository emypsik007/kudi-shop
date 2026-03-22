import os
import logging
import asyncio
import sys
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env файле!")
    exit(1)

# ID разработчика
ADMIN_ID = 1755577918

# URL вашего мини-приложения (ЗАМЕНИТЕ НА СВОЙ!)
WEBAPP_URL = "https://emypsik007.github.io/kudi-shop/mini_app.html"

# Состояния для ConversationHandler
(NAME, PRICE, CATEGORY, IMAGE_URL) = range(4)

# Категории товаров
CATEGORIES = ['hoodies', 'tshirts', 'pants', 'accessories']
CATEGORY_NAMES = {
    'hoodies': '👕 Худи',
    'tshirts': '👕 Футболки',
    'pants': '👖 Штаны',
    'accessories': '🎒 Аксессуары'
}

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            category TEXT NOT NULL,
            image_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Получить все товары
def get_all_products():
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, image_url FROM products ORDER BY id DESC')
    products = cursor.fetchall()
    conn.close()
    return products

# Получить товар по ID
def get_product_by_id(product_id):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, image_url FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

# Добавить товар
def add_product(name, price, category, image_url):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO products (name, price, category, image_url) VALUES (?, ?, ?, ?)',
        (name, price, category, image_url)
    )
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

# Обновить товар
def update_product(product_id, name, price, category, image_url):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE products SET name = ?, price = ?, category = ?, image_url = ? WHERE id = ?',
        (name, price, category, image_url, product_id)
    )
    conn.commit()
    conn.close()

# Удалить товар
def delete_product(product_id):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

# Функция для создания главного меню (без параметра update)
def get_main_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("📢 Канал", url='https://t.me/+ajAM1qe9EBszMmFi')],
        [InlineKeyboardButton("⭐️ Отзывы", url='https://t.me/otzivi_kudishop')],
        [InlineKeyboardButton("🏪 Авито", url='https://www.avito.ru/user/14fc9')],
        [InlineKeyboardButton("🛍️ Магазин", web_app={'url': WEBAPP_URL})]
    ]
    
    # Добавляем админ-панель для разработчика
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])
    
    return InlineKeyboardMarkup(keyboard)

# Функция для создания админ-меню
def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить товар", callback_data='add_product')],
        [InlineKeyboardButton("📋 Список товаров", callback_data='list_products')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("🔙 Назад в магазин", callback_data='back_to_shop')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Создание клавиатуры для выбора категории
def get_category_keyboard():
    keyboard = []
    for cat_id, cat_name in CATEGORY_NAMES.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f'cat_{cat_id}')])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data='cancel_add')])
    return InlineKeyboardMarkup(keyboard)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Получена команда /start от пользователя {user_id}")
    
    welcome_message = """
Добро пожаловать в наш магазин KUDI SHOP 👋

✨ Мгновенный поиск - находите нужный товар за секунды.
💰 Кешбэк - возвращайте часть средств с каждой покупки.
📦 Трекинг заказов - следите за доставкой в реальном времени.
🎁 Промокоды - эксклюзивные предложения только для пользователей бота.
📱 Простой интерфейс — всё под рукой, никаких лишних шагов.
    """
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_menu(user_id)
    )

# Обработчик команды /menu
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=get_main_menu(user_id)
    )

# Обработчик нажатий на инлайн кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    if query.data == 'admin_panel':
        if user_id == ADMIN_ID:
            await query.edit_message_text(
                text="⚙️ *Админ-панель*\n\nВыберите действие:",
                parse_mode='Markdown',
                reply_markup=get_admin_menu()
            )
        else:
            await query.answer("У вас нет доступа к этой функции!", show_alert=True)
    
    elif query.data == 'back_to_shop':
        welcome_message = """
Добро пожаловать в наш магазин KUDI SHOP 👋

✨ Мгновенный поиск - находите нужный товар за секунды.
💰 Кешбэк - возвращайте часть средств с каждой покупки.
📦 Трекинг заказов - следите за доставкой в реальном времени.
🎁 Промокоды - эксклюзивные предложения только для пользователей бота.
📱 Простой интерфейс — всё под рукой, никаких лишних шагов.
        """
        await query.edit_message_text(
            text=welcome_message,
            reply_markup=get_main_menu(user_id)
        )
    
    elif query.data == 'add_product':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        context.user_data['add_product'] = {}
        await query.edit_message_text(
            text="➕ *Добавление нового товара*\n\n"
                 "Введите название товара:",
            parse_mode='Markdown'
        )
        return NAME
    
    elif query.data == 'list_products':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        products = get_all_products()
        
        if not products:
            await query.edit_message_text(
                text="📋 Список товаров пуст.\n\nДобавьте первый товар через кнопку ➕ Добавить товар",
                reply_markup=get_admin_menu()
            )
            return
        
        message = "📋 *Список товаров:*\n\n"
        keyboard = []
        
        for product in products[:10]:  # Показываем первые 10
            product_id, name, price, category, image_url = product
            message += f"🆔 *ID:* {product_id}\n"
            message += f"📦 *Название:* {name}\n"
            message += f"💰 *Цена:* {price} ₽\n"
            message += f"🏷️ *Категория:* {CATEGORY_NAMES.get(category, category)}\n"
            message += f"🖼️ *Изображение:* {image_url}\n"
            message += "➖➖➖➖➖➖➖➖➖➖\n\n"
            
            keyboard.append([InlineKeyboardButton(f"✏️ Редактировать {name[:20]}", callback_data=f'edit_{product_id}')])
            keyboard.append([InlineKeyboardButton(f"🗑️ Удалить {name[:20]}", callback_data=f'delete_{product_id}')])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')])
        
        if len(products) > 10:
            message += f"\n*Всего товаров:* {len(products)}. Показаны первые 10."
        
        await query.edit_message_text(
            text=message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'admin_stats':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        products = get_all_products()
        stats = {}
        for product in products:
            category = product[3]
            stats[category] = stats.get(category, 0) + 1
        
        stats_message = "📊 *Статистика магазина*\n\n"
        stats_message += f"📦 *Всего товаров:* {len(products)}\n\n"
        stats_message += "*По категориям:*\n"
        for cat_id, cat_name in CATEGORY_NAMES.items():
            count = stats.get(cat_id, 0)
            stats_message += f"• {cat_name}: {count}\n"
        
        await query.edit_message_text(
            text=stats_message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='admin_panel')]])
        )
    
    elif query.data.startswith('edit_'):
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        product_id = int(query.data.split('_')[1])
        product = get_product_by_id(product_id)
        
        if not product:
            await query.edit_message_text(
                text="❌ Товар не найден!",
                reply_markup=get_admin_menu()
            )
            return
        
        context.user_data['edit_product'] = {'id': product_id}
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить название", callback_data=f'edit_name_{product_id}')],
            [InlineKeyboardButton("💰 Изменить цену", callback_data=f'edit_price_{product_id}')],
            [InlineKeyboardButton("🏷️ Изменить категорию", callback_data=f'edit_category_{product_id}')],
            [InlineKeyboardButton("🖼️ Изменить фото", callback_data=f'edit_image_{product_id}')],
            [InlineKeyboardButton("🔙 Назад", callback_data='list_products')]
        ]
        
        await query.edit_message_text(
            text=f"✏️ *Редактирование товара*\n\n"
                 f"🆔 ID: {product[0]}\n"
                 f"📦 Название: {product[1]}\n"
                 f"💰 Цена: {product[2]} ₽\n"
                 f"🏷️ Категория: {CATEGORY_NAMES.get(product[3], product[3])}\n"
                 f"🖼️ Фото: {product[4]}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('delete_'):
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        product_id = int(query.data.split('_')[1])
        product = get_product_by_id(product_id)
        
        if product:
            keyboard = [
                [InlineKeyboardButton("✅ Да, удалить", callback_data=f'confirm_delete_{product_id}')],
                [InlineKeyboardButton("❌ Нет, отмена", callback_data='list_products')]
            ]
            
            await query.edit_message_text(
                text=f"⚠️ *Подтверждение удаления*\n\n"
                     f"Вы уверены, что хотите удалить товар?\n\n"
                     f"📦 {product[1]}\n💰 {product[2]} ₽",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    elif query.data.startswith('confirm_delete_'):
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        
        product_id = int(query.data.split('_')[2])
        delete_product(product_id)
        
        await query.edit_message_text(
            text="✅ Товар успешно удален!",
            reply_markup=get_admin_menu()
        )
    
    elif query.data.startswith('edit_name_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'name', 'id': product_id}
        await query.edit_message_text(
            text="✏️ Введите новое название товара:",
            parse_mode='Markdown'
        )
        return NAME
    
    elif query.data.startswith('edit_price_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'price', 'id': product_id}
        await query.edit_message_text(
            text="💰 Введите новую цену товара (только число):",
            parse_mode='Markdown'
        )
        return PRICE
    
    elif query.data.startswith('edit_category_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'category', 'id': product_id}
        await query.edit_message_text(
            text="🏷️ Выберите новую категорию:",
            parse_mode='Markdown',
            reply_markup=get_category_keyboard()
        )
        return CATEGORY
    
    elif query.data.startswith('edit_image_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'image', 'id': product_id}
        await query.edit_message_text(
            text="🖼️ Введите URL нового изображения:",
            parse_mode='Markdown'
        )
        return IMAGE_URL
    
    elif query.data.startswith('cat_'):
        category = query.data.split('_')[1]
        
        if 'add_product' in context.user_data:
            context.user_data['add_product']['category'] = category
            await query.edit_message_text(
                text="🖼️ Введите URL изображения товара:"
            )
            return IMAGE_URL
        elif 'edit_field' in context.user_data:
            field_data = context.user_data['edit_field']
            if field_data['type'] == 'category':
                product = get_product_by_id(field_data['id'])
                if product:
                    update_product(field_data['id'], product[1], product[2], category, product[4])
                    await query.edit_message_text(
                        text="✅ Категория успешно обновлена!",
                        reply_markup=get_admin_menu()
                    )
                    del context.user_data['edit_field']
                return ConversationHandler.END
    
    elif query.data == 'cancel_add':
        if 'add_product' in context.user_data:
            del context.user_data['add_product']
        await query.edit_message_text(
            text="❌ Добавление товара отменено.",
            reply_markup=get_admin_menu()
        )
        return ConversationHandler.END

# Обработчик названия товара
async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data['add_product']['name'] = name
    
    await update.message.reply_text(
        "💰 Введите цену товара (только число):"
    )
    return PRICE

# Обработчик цены товара
async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        if price <= 0:
            raise ValueError
        context.user_data['add_product']['price'] = price
        
        await update.message.reply_text(
            "🏷️ Выберите категорию товара:",
            reply_markup=get_category_keyboard()
        )
        return CATEGORY
    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное число (больше 0).\n\n"
            "Введите цену товара:"
        )
        return PRICE

# Обработчик изображения товара
async def add_product_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    image_url = update.message.text
    
    if not image_url.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректный URL (должен начинаться с http:// или https://)\n\n"
            "Введите URL изображения:"
        )
        return IMAGE_URL
    
    product_data = context.user_data['add_product']
    
    add_product(
        product_data['name'],
        product_data['price'],
        product_data['category'],
        image_url
    )
    
    await update.message.reply_text(
        f"✅ Товар успешно добавлен!\n\n"
        f"📦 *{product_data['name']}*\n"
        f"💰 {product_data['price']} ₽\n"
        f"🏷️ Категория: {CATEGORY_NAMES.get(product_data['category'], product_data['category'])}",
        parse_mode='Markdown',
        reply_markup=get_admin_menu()
    )
    
    del context.user_data['add_product']
    return ConversationHandler.END

# Обработчик редактирования поля
async def edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field_data = context.user_data.get('edit_field')
    if not field_data:
        await update.message.reply_text("❌ Ошибка! Попробуйте снова.", reply_markup=get_admin_menu())
        return ConversationHandler.END
    
    product = get_product_by_id(field_data['id'])
    if not product:
        await update.message.reply_text("❌ Товар не найден!", reply_markup=get_admin_menu())
        return ConversationHandler.END
    
    if field_data['type'] == 'name':
        new_value = update.message.text
        update_product(field_data['id'], new_value, product[2], product[3], product[4])
        await update.message.reply_text(f"✅ Название изменено на: {new_value}", reply_markup=get_admin_menu())
    
    elif field_data['type'] == 'price':
        try:
            new_value = int(update.message.text)
            if new_value <= 0:
                raise ValueError
            update_product(field_data['id'], product[1], new_value, product[3], product[4])
            await update.message.reply_text(f"✅ Цена изменена на: {new_value} ₽", reply_markup=get_admin_menu())
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите корректное число (больше 0).", reply_markup=get_admin_menu())
    
    elif field_data['type'] == 'image':
        new_value = update.message.text
        if not new_value.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ Пожалуйста, введите корректный URL (должен начинаться с http:// или https://)", reply_markup=get_admin_menu())
            return IMAGE_URL
        update_product(field_data['id'], product[1], product[2], product[3], new_value)
        await update.message.reply_text(f"✅ URL изображения изменен", reply_markup=get_admin_menu())
    
    del context.user_data['edit_field']
    return ConversationHandler.END

# Обработчик данных из WebApp
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data.data
    logger.info(f"Получены данные из WebApp: {data}")
    
    user = update.effective_user
    
    try:
        order = json.loads(data)
        
        if order.get('action') == 'order':
            order_text = "🛍️ *Новый заказ!*\n\n"
            order_text += f"👤 *Клиент:* @{user.username if user.username else 'неизвестно'}\n"
            order_text += f"📛 *Имя:* {user.first_name}\n"
            order_text += f"🆔 *ID:* {user.id}\n"
            order_text += "📦 *Товары:*\n"
            
            for item in order['cart']:
                order_text += f"• {item['name']} x{item['quantity']} — {item['price'] * item['quantity']} ₽\n"
            
            order_text += f"\n💰 *Итого:* {order['total']} ₽"
            
            # Сохраняем заказ в файл
            orders_file = 'orders.json'
            orders = []
            if os.path.exists(orders_file):
                with open(orders_file, 'r', encoding='utf-8') as f:
                    orders = json.load(f)
            
            order_record = {
                'id': len(orders) + 1,
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'date': datetime.now().isoformat(),
                'items': order['cart'],
                'total': order['total']
            }
            orders.append(order_record)
            
            with open(orders_file, 'w', encoding='utf-8') as f:
                json.dump(orders, f, ensure_ascii=False, indent=2)
            
            await update.message.reply_text(order_text, parse_mode='Markdown')
            
            # Отправляем уведомление админу
            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🛍️ *НОВЫЙ ЗАКАЗ!*\n\n"
                         f"👤 {user.first_name} (@{user.username})\n"
                         f"💰 Сумма: {order['total']} ₽\n"
                         f"📦 Товаров: {len(order['cart'])}",
                    parse_mode='Markdown'
                )
            
            await update.message.reply_text(
                "✅ Заказ оформлен! Наш менеджер свяжется с вами в ближайшее время.",
                reply_markup=get_main_menu(user.id)
            )
    except Exception as e:
        logger.error(f"Ошибка обработки заказа: {e}")
        await update.message.reply_text("Произошла ошибка при оформлении заказа. Попробуйте позже.")

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()
    
    if 'канал' in text:
        await update.message.reply_text(
            "Наш канал:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 Перейти на канал", url='https://t.me/+ajAM1qe9EBszMmFi')
            ]])
        )
    elif 'отзыв' in text:
        await update.message.reply_text(
            "Отзывы о нас:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐️ Читать отзывы", url='https://t.me/otzivi_kudishop')
            ]])
        )
    elif 'авито' in text:
        await update.message.reply_text(
            "Наш магазин на Авито:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏪 Перейти на Авито", url='https://www.avito.ru/user/14fc9')
            ]])
        )
    else:
        await update.message.reply_text(
            "Используйте кнопки меню или команду /start",
            reply_markup=get_main_menu(user_id)
        )

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    # Инициализируем базу данных
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler для добавления товара
    add_product_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern='^add_product$')],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            CATEGORY: [CallbackQueryHandler(button_callback, pattern='^cat_')],
            IMAGE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_image)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )
    
    # Conversation handler для редактирования
    edit_product_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern='^edit_name_'),
            CallbackQueryHandler(button_callback, pattern='^edit_price_'),
            CallbackQueryHandler(button_callback, pattern='^edit_image_')
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
            IMAGE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^list_products$')],
        per_message=False,
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(add_product_handler)
    application.add_handler(edit_product_handler)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("Бот запущен в режиме long polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()