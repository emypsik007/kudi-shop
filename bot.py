import os
import logging
import asyncio
import sys
import json
import sqlite3
import base64
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

# URL вашего мини-приложения
WEBAPP_URL = "https://emypsik007.github.io/kudi-shop/mini_app.html"

# Состояния для ConversationHandler
(NAME, PRICE, CATEGORY, PHOTOS) = range(4)

# Категории товаров
CATEGORIES = ['hoodies', 'tshirts', 'pants', 'accessories']
CATEGORY_NAMES = {
    'hoodies': '👕 Худи',
    'tshirts': '👕 Футболки',
    'pants': '👖 Штаны',
    'accessories': '🎒 Аксессуары'
}

# Создаем папку для фото если её нет
os.makedirs('product_photos', exist_ok=True)

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
            photos TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Получить все товары
def get_all_products():
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, photos FROM products ORDER BY id DESC')
    products = cursor.fetchall()
    conn.close()
    return products

# Получить товар по ID
def get_product_by_id(product_id):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, photos FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

# Добавить товар
def add_product(name, price, category, photos):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO products (name, price, category, photos) VALUES (?, ?, ?, ?)',
        (name, price, category, json.dumps(photos))
    )
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return product_id

# Обновить товар
def update_product(product_id, name, price, category, photos):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE products SET name = ?, price = ?, category = ?, photos = ? WHERE id = ?',
        (name, price, category, json.dumps(photos), product_id)
    )
    conn.commit()
    conn.close()

# Удалить товар
def delete_product(product_id):
    # Получаем пути к фото перед удалением
    product = get_product_by_id(product_id)
    if product:
        photos = json.loads(product[4])
        for photo_path in photos:
            if os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except:
                    pass
    
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

# Функция для создания главного меню
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

# Получить список товаров для отправки в WebApp
def get_products_for_webapp():
    products = get_all_products()
    products_list = []
    
    for product in products:
        photos = json.loads(product[4]) if product[4] else []
        photos_data = []
        
        for photo_path in photos[:3]:  # Отправляем первые 3 фото
            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as f:
                    photo_base64 = base64.b64encode(f.read()).decode('utf-8')
                    photos_data.append(f"data:image/jpeg;base64,{photo_base64}")
        
        products_list.append({
            'id': product[0],
            'name': product[1],
            'price': product[2],
            'category': product[3],
            'photos': photos_data,
            'main_photo': photos_data[0] if photos_data else None
        })
    
    return products_list

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

# Обработчик названия товара
async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data['add_product'] = context.user_data.get('add_product', {})
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

# Обработчик категории (через кнопки)
async def add_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category = query.data.split('_')[1]
    context.user_data['add_product']['category'] = category
    
    # Инициализируем список фото
    if 'photos' not in context.user_data['add_product']:
        context.user_data['add_product']['photos'] = []
    
    await query.edit_message_text(
        text="📸 Отправьте фото товара (можно до 5 штук).\n\n"
             "Просто отправьте фото из галереи или сделайте новое.\n"
             "После каждого фото вы сможете добавить еще или завершить."
    )
    return PHOTOS

# Обработчик добавления фото
async def add_product_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения фото для товара"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для добавления товаров!")
        return ConversationHandler.END
    
    if 'add_product' not in context.user_data:
        context.user_data['add_product'] = {}
    
    # Получаем фото
    if 'photos' not in context.user_data['add_product']:
        context.user_data['add_product']['photos'] = []
    
    # Проверяем, есть ли фото в сообщении
    if update.message.photo:
        # Получаем самое большое фото
        photo_file = await update.message.photo[-1].get_file()
        timestamp = int(datetime.now().timestamp())
        filename = f"{context.user_data['add_product']['name']}_{len(context.user_data['add_product']['photos'])+1}_{timestamp}.jpg"
        # Очищаем имя файла от недопустимых символов
        filename = "".join(c for c in filename if c.isalnum() or c in '._-')
        file_path = f"product_photos/{filename}"
        
        # Скачиваем фото
        await photo_file.download_to_drive(file_path)
        
        # Сохраняем путь к фото
        context.user_data['add_product']['photos'].append(file_path)
        
        # Проверяем сколько фото уже добавлено
        photos_count = len(context.user_data['add_product']['photos'])
        
        if photos_count >= 5:
            # Если достигли лимита, завершаем добавление
            product_data = context.user_data['add_product']
            
            add_product(
                product_data['name'],
                product_data['price'],
                product_data['category'],
                product_data['photos']
            )
            
            # Отправляем превью с первым фото
            with open(product_data['photos'][0], 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"✅ Товар успешно добавлен!\n\n"
                           f"📦 *{product_data['name']}*\n"
                           f"💰 {product_data['price']} ₽\n"
                           f"🏷️ Категория: {CATEGORY_NAMES.get(product_data['category'], product_data['category'])}\n"
                           f"📸 Фото: {len(product_data['photos'])} шт.",
                    parse_mode='Markdown',
                    reply_markup=get_admin_menu()
                )
            
            del context.user_data['add_product']
            return ConversationHandler.END
        else:
            # Предлагаем добавить еще фото или завершить
            keyboard = [
                [InlineKeyboardButton("📸 Добавить еще фото", callback_data='add_more_photos')],
                [InlineKeyboardButton("✅ Завершить добавление", callback_data='finish_adding_product')]
            ]
            await update.message.reply_text(
                f"📸 Фото {photos_count}/5 добавлено!\n\n"
                f"Вы можете добавить еще фото или завершить добавление товара.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return PHOTOS
    else:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте фото.\n\n"
            "Или используйте кнопки:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Завершить добавление", callback_data='finish_adding_product')]
            ])
        )
        return PHOTOS

# Обработчик нажатий на инлайн кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    # Обработка добавления фото
    if query.data == 'add_more_photos':
        await query.edit_message_text(
            "📸 Отправьте следующее фото товара:"
        )
        return PHOTOS
    
    elif query.data == 'finish_adding_product':
        if 'add_product' in context.user_data:
            product_data = context.user_data['add_product']
            if product_data.get('photos') and len(product_data['photos']) > 0:
                add_product(
                    product_data['name'],
                    product_data['price'],
                    product_data['category'],
                    product_data['photos']
                )
                
                # Отправляем превью с первым фото
                with open(product_data['photos'][0], 'rb') as photo:
                    await query.message.reply_photo(
                        photo=photo,
                        caption=f"✅ Товар успешно добавлен!\n\n"
                               f"📦 *{product_data['name']}*\n"
                               f"💰 {product_data['price']} ₽\n"
                               f"🏷️ Категория: {CATEGORY_NAMES.get(product_data['category'], product_data['category'])}\n"
                               f"📸 Фото: {len(product_data['photos'])} шт.",
                        parse_mode='Markdown',
                        reply_markup=get_admin_menu()
                    )
                
                del context.user_data['add_product']
                await query.delete_message()
            else:
                await query.edit_message_text(
                    "❌ Нужно добавить хотя бы одно фото товара!\n\n"
                    "Отправьте фото:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Отмена", callback_data='cancel_add')]
                    ])
                )
                return PHOTOS
        return ConversationHandler.END
    
    # Обработка выбора категории при добавлении товара
    if query.data.startswith('cat_') and 'add_product' in context.user_data:
        category = query.data.split('_')[1]
        context.user_data['add_product']['category'] = category
        
        # Инициализируем список фото
        if 'photos' not in context.user_data['add_product']:
            context.user_data['add_product']['photos'] = []
        
        await query.edit_message_text(
            text="📸 Отправьте фото товара (можно до 5 штук).\n\n"
                 "Просто отправьте фото из галереи или сделайте новое.\n"
                 "После каждого фото вы сможете добавить еще или завершить."
        )
        return PHOTOS
    
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
        
        for product in products[:10]:
            product_id, name, price, category, photos_json = product
            photos = json.loads(photos_json)
            message += f"🆔 *ID:* {product_id}\n"
            message += f"📦 *Название:* {name}\n"
            message += f"💰 *Цена:* {price} ₽\n"
            message += f"🏷️ *Категория:* {CATEGORY_NAMES.get(category, category)}\n"
            message += f"📸 *Фото:* {len(photos)} шт.\n"
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
    
    elif query.data.startswith('edit_') and not query.data.startswith('edit_name_') and not query.data.startswith('edit_price_') and not query.data.startswith('edit_category_') and not query.data.startswith('edit_photos_'):
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
        
        photos = json.loads(product[4])
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить название", callback_data=f'edit_name_{product_id}')],
            [InlineKeyboardButton("💰 Изменить цену", callback_data=f'edit_price_{product_id}')],
            [InlineKeyboardButton("🏷️ Изменить категорию", callback_data=f'edit_category_{product_id}')],
            [InlineKeyboardButton("📸 Изменить фото", callback_data=f'edit_photos_{product_id}')],
            [InlineKeyboardButton("🔙 Назад", callback_data='list_products')]
        ]
        
        await query.edit_message_text(
            text=f"✏️ *Редактирование товара*\n\n"
                 f"🆔 ID: {product[0]}\n"
                 f"📦 Название: {product[1]}\n"
                 f"💰 Цена: {product[2]} ₽\n"
                 f"🏷️ Категория: {CATEGORY_NAMES.get(product[3], product[3])}\n"
                 f"📸 Фото: {len(photos)} шт.",
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
    
    elif query.data.startswith('edit_photos_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'photos', 'id': product_id}
        context.user_data['edit_photos'] = []
        await query.edit_message_text(
            text="📸 Отправьте новые фото товара (можно до 5 штук).\n"
                 "Старые фото будут заменены.",
            parse_mode='Markdown'
        )
        return PHOTOS
    
    elif query.data == 'cancel_add':
        if 'add_product' in context.user_data:
            # Удаляем загруженные фото
            photos = context.user_data['add_product'].get('photos', [])
            for photo_path in photos:
                if os.path.exists(photo_path):
                    try:
                        os.remove(photo_path)
                    except:
                        pass
            del context.user_data['add_product']
        if 'edit_field' in context.user_data:
            del context.user_data['edit_field']
        await query.edit_message_text(
            text="❌ Действие отменено.",
            reply_markup=get_admin_menu()
        )
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
        photos = json.loads(product[4])
        update_product(field_data['id'], new_value, product[2], product[3], photos)
        await update.message.reply_text(f"✅ Название изменено на: {new_value}", reply_markup=get_admin_menu())
    
    elif field_data['type'] == 'price':
        try:
            new_value = int(update.message.text)
            if new_value <= 0:
                raise ValueError
            photos = json.loads(product[4])
            update_product(field_data['id'], product[1], new_value, product[3], photos)
            await update.message.reply_text(f"✅ Цена изменена на: {new_value} ₽", reply_markup=get_admin_menu())
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите корректное число (больше 0).", reply_markup=get_admin_menu())
            return PRICE
    
    elif field_data['type'] == 'category':
        # Категория обрабатывается через callback
        pass
    
    elif field_data['type'] == 'photos':
        if update.message.photo:
            # Получаем фото
            if 'edit_photos' not in context.user_data:
                context.user_data['edit_photos'] = []
            
            photo_file = await update.message.photo[-1].get_file()
            timestamp = int(datetime.now().timestamp())
            filename = f"{product[1]}_edit_{len(context.user_data['edit_photos'])+1}_{timestamp}.jpg"
            filename = "".join(c for c in filename if c.isalnum() or c in '._-')
            file_path = f"product_photos/{filename}"
            
            await photo_file.download_to_drive(file_path)
            context.user_data['edit_photos'].append(file_path)
            
            if len(context.user_data['edit_photos']) >= 5:
                # Завершаем обновление фото
                update_product(field_data['id'], product[1], product[2], product[3], context.user_data['edit_photos'])
                
                # Отправляем превью
                with open(context.user_data['edit_photos'][0], 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=f"✅ Фото товара обновлены! Загружено {len(context.user_data['edit_photos'])} фото.",
                        reply_markup=get_admin_menu()
                    )
                
                del context.user_data['edit_field']
                del context.user_data['edit_photos']
                return ConversationHandler.END
            else:
                keyboard = [
                    [InlineKeyboardButton("📸 Добавить еще фото", callback_data='add_more_edit_photos')],
                    [InlineKeyboardButton("✅ Завершить обновление", callback_data='finish_edit_photos')]
                ]
                await update.message.reply_text(
                    f"📸 Фото {len(context.user_data['edit_photos'])}/5 добавлено!\n\n"
                    f"Вы можете добавить еще фото или завершить обновление.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return PHOTOS
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте фото.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Завершить обновление", callback_data='finish_edit_photos')]
                ])
            )
            return PHOTOS
    
    del context.user_data['edit_field']
    return ConversationHandler.END

# Обработчик данных из WebApp
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data.data
    logger.info(f"Получены данные из WebApp: {data}")
    
    user = update.effective_user
    
    try:
        request = json.loads(data)
        
        # Обработка запроса на получение списка товаров
        if request.get('action') == 'get_products':
            products_list = get_products_for_webapp()
            
            # Кодируем товары в JSON для передачи через URL
            products_json = json.dumps(products_list)
            import urllib.parse
            products_encoded = urllib.parse.quote(products_json)
            
            # Отправляем сообщение с кнопкой, которая передаст товары через URL параметр
            await update.message.reply_text(
                f"🛍️ *Магазин KUDI SHOP*\n\n"
                f"📦 Товаров в наличии: {len(products_list)}\n\n"
                f"Нажмите на кнопку ниже, чтобы открыть магазин с товарами:",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🛍️ Открыть магазин",
                        web_app={'url': f"{WEBAPP_URL}?products={products_encoded}"}
                    )
                ]])
            )
            
            # Также отправляем простое сообщение для отладки
            if products_list:
                preview_text = "📋 *Товары в базе:*\n\n"
                for i, p in enumerate(products_list[:10]):
                    preview_text += f"{i+1}. {p['name']} - {p['price']} ₽\n"
                if len(products_list) > 10:
                    preview_text += f"\n*...и еще {len(products_list) - 10} товаров*"
                
                await context.bot.send_message(
                    chat_id=user.id,
                    text=preview_text,
                    parse_mode='Markdown'
                )
            
            return
        
        # Обработка оформления заказа
        elif request.get('action') == 'order':
            order_text = "🛍️ *Новый заказ!*\n\n"
            order_text += f"👤 *Клиент:* @{user.username if user.username else 'неизвестно'}\n"
            order_text += f"📛 *Имя:* {user.first_name}\n"
            order_text += f"🆔 *ID:* {user.id}\n"
            order_text += "📦 *Товары:*\n"
            
            for item in request['cart']:
                order_text += f"• {item['name']} x{item['quantity']} — {item['price'] * item['quantity']} ₽\n"
            
            order_text += f"\n💰 *Итого:* {request['total']} ₽"
            
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
                'items': request['cart'],
                'total': request['total']
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
                         f"💰 Сумма: {request['total']} ₽\n"
                         f"📦 Товаров: {len(request['cart'])}",
                    parse_mode='Markdown'
                )
            
            await update.message.reply_text(
                "✅ Заказ оформлен! Наш менеджер свяжется с вами в ближайшее время.",
                reply_markup=get_main_menu(user.id)
            )
    
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        await update.message.reply_text("Произошла ошибка при обработке данных.")
    except Exception as e:
        logger.error(f"Ошибка обработки данных из WebApp: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса. Попробуйте позже.")

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
            PHOTOS: [MessageHandler(filters.PHOTO, add_product_photos)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )
    
    # Conversation handler для редактирования
    edit_product_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern='^edit_name_'),
            CallbackQueryHandler(button_callback, pattern='^edit_price_'),
            CallbackQueryHandler(button_callback, pattern='^edit_photos_'),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
            PHOTOS: [MessageHandler(filters.PHOTO, edit_field_value)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )
    
    # Conversation handler для категории при редактировании
    edit_category_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern='^edit_category_')],
        states={
            CATEGORY: [CallbackQueryHandler(button_callback, pattern='^cat_')],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(add_product_handler)
    application.add_handler(edit_product_handler)
    application.add_handler(edit_category_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("Бот запущен в режиме long polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
