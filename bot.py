import os
import logging
import asyncio
import sys
import json
import sqlite3
import base64
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в .env файле!")
    exit(1)

ADMIN_ID = 1755577918

WEBAPP_URL = "https://emypsik007.github.io/kudi-shop/mini_app.html"

# ── Публикация фото в GitHub Pages ───────────────────────────────
PHOTOS_DIR = 'product_photos'
GH_PAGES_DIR = 'kudi-shop/product_photos'
GH_REPO_DIR = 'kudi-shop'
PHOTO_BASE_URL = "https://emypsik007.github.io/kudi-shop/product_photos/"
GIT_AUTO_PUSH = True

# Состояния
(NAME, PRICE, CATEGORY, PHOTOS) = range(4)

CATEGORIES = ['hoodies', 'tshirts', 'pants', 'accessories']
CATEGORY_NAMES = {
    'hoodies': 'Худи',
    'tshirts': 'Футболки',
    'pants': 'Штаны',
    'accessories': 'Аксессуары'
}

os.makedirs(PHOTOS_DIR, exist_ok=True)


# ── GitHub Pages ─────────────────────────────────────────────────
def publish_photo_to_pages(local_path: str) -> str:
    try:
        os.makedirs(GH_PAGES_DIR, exist_ok=True)
        filename = os.path.basename(local_path)
        dst = os.path.join(GH_PAGES_DIR, filename)
        if os.path.abspath(local_path) != os.path.abspath(dst):
            shutil.copy2(local_path, dst)
        return PHOTO_BASE_URL + filename
    except Exception as e:
        logger.error(f"Не удалось опубликовать фото {local_path}: {e}")
        return ""


def git_push_pages(commit_msg: str = "update product photos"):
    if not GIT_AUTO_PUSH:
        return
    try:
        if not os.path.isdir(os.path.join(GH_REPO_DIR, '.git')):
            logger.warning(f"Git-репозиторий не найден: {GH_REPO_DIR}")
            return
        subprocess.run(['git', '-C', GH_REPO_DIR, 'add', '.'], check=True, capture_output=True)
        diff = subprocess.run(['git', '-C', GH_REPO_DIR, 'diff', '--cached', '--quiet'], capture_output=True)
        if diff.returncode == 0:
            logger.info("Нечего коммитить в GitHub Pages")
            return
        subprocess.run(['git', '-C', GH_REPO_DIR, 'commit', '-m', commit_msg], check=True, capture_output=True)
        subprocess.run(['git', '-C', GH_REPO_DIR, 'push'], check=True, capture_output=True)
        logger.info(f"GitHub Pages обновлён: {commit_msg}")
    except Exception as e:
        logger.error(f"Ошибка git push: {e}")


def cleanup_orphan_photos():
    try:
        if not os.path.isdir(GH_PAGES_DIR):
            return
        all_products = get_all_products()
        used = set()
        for p in all_products:
            try:
                for ph in json.loads(p[4]):
                    used.add(os.path.basename(ph))
            except Exception:
                pass
        removed = 0
        for f in os.listdir(GH_PAGES_DIR):
            if f not in used:
                try:
                    os.remove(os.path.join(GH_PAGES_DIR, f))
                    removed += 1
                except Exception:
                    pass
        if removed:
            git_push_pages(f"cleanup {removed} orphan photos")
    except Exception as e:
        logger.error(f"Ошибка cleanup_orphan_photos: {e}")


# ── БД ───────────────────────────────────────────────────────────
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


def get_all_products():
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, photos FROM products ORDER BY id DESC')
    products = cursor.fetchall()
    conn.close()
    return products


def get_product_by_id(product_id):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, photos FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product


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


def update_product(product_id, name, price, category, photos):
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE products SET name = ?, price = ?, category = ?, photos = ? WHERE id = ?',
        (name, price, category, json.dumps(photos), product_id)
    )
    conn.commit()
    conn.close()


def delete_product(product_id):
    product = get_product_by_id(product_id)
    if product:
        photos = json.loads(product[4])
        for photo_path in photos:
            if os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except Exception:
                    pass
            gh_path = os.path.join(GH_PAGES_DIR, os.path.basename(photo_path))
            if os.path.exists(gh_path):
                try:
                    os.remove(gh_path)
                except Exception:
                    pass

    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    git_push_pages(f"delete product #{product_id}")


# ── Передача товаров в WebApp ────────────────────────────────────
def encode_products_payload(data):
    """base64url(JSON) без сжатия — надёжно работает во всех WebView."""
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return base64.urlsafe_b64encode(json_str.encode('utf-8')).decode('ascii').rstrip('=')


def get_products_for_webapp():
    products = get_all_products()
    result = []
    for p in products:
        photos = json.loads(p[4]) if p[4] else []
        urls = [publish_photo_to_pages(ph) for ph in photos]
        urls = [u for u in urls if u]
        result.append({
            'id': p[0],
            'name': p[1],
            'price': p[2],
            'category': p[3],
            'photos': urls,
            'main_photo': urls[0] if urls else None,
        })
    return result


def build_shop_url():
    products_data = get_products_for_webapp()
    if not products_data:
        return WEBAPP_URL

    # Пробуем влезть целиком
    encoded = encode_products_payload(products_data)
    if len(encoded) < 3600:
        return f"{WEBAPP_URL}?d={encoded}"

    # Обрезаем — берём самые свежие N товаров
    logger.warning(f"URL слишком длинный ({len(encoded)}), обрезаем список")
    for n in (40, 30, 20, 10):
        short = products_data[:n]
        encoded = encode_products_payload(short)
        if len(encoded) < 3800:
            return f"{WEBAPP_URL}?d={encoded}"

    return WEBAPP_URL


# ── Меню ─────────────────────────────────────────────────────────
def get_main_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("Канал", url='https://t.me/+ajAM1qe9EBszMmFi')],
        [InlineKeyboardButton("Отзывы", url='https://t.me/otzivi_kudishop')],
        [InlineKeyboardButton("Авито", url='https://www.avito.ru/user/14fc9')],
    ]

    shop_url = build_shop_url()
    keyboard.append([InlineKeyboardButton("Магазин", web_app={'url': shop_url})])

    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Админ-панель", callback_data='admin_panel')])

    return InlineKeyboardMarkup(keyboard)


def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("Добавить товар", callback_data='add_product')],
        [InlineKeyboardButton("Список товаров", callback_data='list_products')],
        [InlineKeyboardButton("Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("Очистить лишние фото", callback_data='cleanup_photos')],
        [InlineKeyboardButton("Назад в магазин", callback_data='back_to_shop')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard():
    keyboard = []
    for cat_id, cat_name in CATEGORY_NAMES.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f'cat_{cat_id}')])
    keyboard.append([InlineKeyboardButton("Отмена", callback_data='cancel_add')])
    return InlineKeyboardMarkup(keyboard)


# ── Команды ──────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"/start от {user_id}")

    welcome_message = (
        "Добро пожаловать в KUDI SHOP\n\n"
        "Мгновенный поиск — находите нужный товар за секунды.\n"
        "Кешбэк — возвращайте часть средств с каждой покупки.\n"
        "Трекинг заказов — следите за доставкой в реальном времени.\n"
        "Промокоды — эксклюзивные предложения для пользователей бота.\n"
        "Простой интерфейс — всё под рукой."
    )

    await update.message.reply_text(welcome_message, reply_markup=get_main_menu(user_id))


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("Главное меню:", reply_markup=get_main_menu(user_id))


# ── Добавление товара ────────────────────────────────────────────
async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data['add_product'] = context.user_data.get('add_product', {})
    context.user_data['add_product']['name'] = name
    await update.message.reply_text("Введите цену товара (только число):")
    return PRICE


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        if price <= 0:
            raise ValueError
        context.user_data['add_product']['price'] = price
        await update.message.reply_text(
            "Выберите категорию товара:",
            reply_markup=get_category_keyboard()
        )
        return CATEGORY
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите корректное число (больше 0).\n\nВведите цену товара:"
        )
        return PRICE


async def add_product_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас нет прав для добавления товаров!")
        return ConversationHandler.END

    if 'add_product' not in context.user_data:
        context.user_data['add_product'] = {}
    if 'photos' not in context.user_data['add_product']:
        context.user_data['add_product']['photos'] = []

    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        timestamp = int(datetime.now().timestamp())
        product_name = context.user_data['add_product'].get('name', 'product')
        filename = f"{product_name}_{len(context.user_data['add_product']['photos'])+1}_{timestamp}.jpg"
        filename = "".join(c for c in filename if c.isalnum() or c in '._-')
        file_path = f"{PHOTOS_DIR}/{filename}"

        await photo_file.download_to_drive(file_path)
        context.user_data['add_product']['photos'].append(file_path)

        photos_count = len(context.user_data['add_product']['photos'])

        if photos_count >= 5:
            product_data = context.user_data['add_product']

            add_product(
                product_data['name'],
                product_data['price'],
                product_data['category'],
                product_data['photos']
            )

            for ph in product_data['photos']:
                publish_photo_to_pages(ph)
            git_push_pages(f"add product: {product_data['name']}")

            with open(product_data['photos'][0], 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=(
                        f"Товар успешно добавлен!\n\n"
                        f"Название: {product_data['name']}\n"
                        f"Цена: {product_data['price']} руб.\n"
                        f"Категория: {CATEGORY_NAMES.get(product_data['category'], product_data['category'])}\n"
                        f"Фото: {len(product_data['photos'])} шт."
                    ),
                    reply_markup=get_admin_menu()
                )

            del context.user_data['add_product']
            return ConversationHandler.END
        else:
            keyboard = [
                [InlineKeyboardButton("Добавить еще фото", callback_data='add_more_photos')],
                [InlineKeyboardButton("Завершить добавление", callback_data='finish_adding_product')]
            ]
            await update.message.reply_text(
                f"Фото {photos_count}/5 добавлено.\n\n"
                f"Добавьте еще фото или завершите.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return PHOTOS
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте фото.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Завершить добавление", callback_data='finish_adding_product')]
            ])
        )
        return PHOTOS


# ── Универсальный обработчик кнопок ──────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'add_more_photos':
        await query.edit_message_text("Отправьте следующее фото товара:")
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

                for ph in product_data['photos']:
                    publish_photo_to_pages(ph)
                git_push_pages(f"add product: {product_data['name']}")

                with open(product_data['photos'][0], 'rb') as photo:
                    await query.message.reply_photo(
                        photo=photo,
                        caption=(
                            f"Товар успешно добавлен!\n\n"
                            f"Название: {product_data['name']}\n"
                            f"Цена: {product_data['price']} руб.\n"
                            f"Категория: {CATEGORY_NAMES.get(product_data['category'], product_data['category'])}\n"
                            f"Фото: {len(product_data['photos'])} шт."
                        ),
                        reply_markup=get_admin_menu()
                    )

                del context.user_data['add_product']
                try:
                    await query.delete_message()
                except Exception:
                    pass
            else:
                await query.edit_message_text(
                    "Нужно добавить хотя бы одно фото товара!\n\nОтправьте фото:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Отмена", callback_data='cancel_add')]
                    ])
                )
                return PHOTOS
        return ConversationHandler.END

    # Категория для добавления
    if query.data.startswith('cat_') and 'add_product' in context.user_data:
        category = query.data.split('_')[1]
        context.user_data['add_product']['category'] = category

        if 'photos' not in context.user_data['add_product']:
            context.user_data['add_product']['photos'] = []

        await query.edit_message_text(
            "Отправьте фото товара (можно до 5 штук).\n\n"
            "После каждого фото вы сможете добавить еще или завершить."
        )
        return PHOTOS

    # Категория для редактирования
    if query.data.startswith('cat_') and 'edit_field' in context.user_data:
        field = context.user_data['edit_field']
        if field.get('type') == 'category':
            new_cat = query.data.split('_')[1]
            product = get_product_by_id(field['id'])
            if product:
                photos = json.loads(product[4])
                update_product(field['id'], product[1], product[2], new_cat, photos)
                await query.edit_message_text(
                    f"Категория изменена на: {CATEGORY_NAMES.get(new_cat, new_cat)}",
                    reply_markup=get_admin_menu()
                )
            del context.user_data['edit_field']
            return ConversationHandler.END

    if query.data == 'admin_panel':
        if user_id == ADMIN_ID:
            await query.edit_message_text(
                "Админ-панель\n\nВыберите действие:",
                reply_markup=get_admin_menu()
            )
        else:
            await query.answer("У вас нет доступа к этой функции!", show_alert=True)

    elif query.data == 'back_to_shop':
        welcome_message = (
            "Добро пожаловать в KUDI SHOP\n\n"
            "Мгновенный поиск — находите нужный товар за секунды.\n"
            "Кешбэк — возвращайте часть средств с каждой покупки.\n"
            "Трекинг заказов — следите за доставкой в реальном времени.\n"
            "Промокоды — эксклюзивные предложения для пользователей бота.\n"
            "Простой интерфейс — всё под рукой."
        )
        await query.edit_message_text(
            welcome_message,
            reply_markup=get_main_menu(user_id)
        )

    elif query.data == 'add_product':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return

        context.user_data['add_product'] = {}
        await query.edit_message_text("Добавление нового товара\n\nВведите название товара:")
        return NAME

    elif query.data == 'list_products':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return

        products = get_all_products()

        if not products:
            await query.edit_message_text(
                "Список товаров пуст.\n\nДобавьте первый товар через кнопку \"Добавить товар\"",
                reply_markup=get_admin_menu()
            )
            return

        message = "Список товаров:\n\n"
        keyboard = []

        for product in products[:10]:
            product_id, name, price, category, photos_json = product
            photos = json.loads(photos_json)
            message += f"ID: {product_id}\n"
            message += f"Название: {name}\n"
            message += f"Цена: {price} руб.\n"
            message += f"Категория: {CATEGORY_NAMES.get(category, category)}\n"
            message += f"Фото: {len(photos)} шт.\n"
            message += "────────────────\n\n"

            keyboard.append([InlineKeyboardButton(f"Редактировать {name[:20]}", callback_data=f'edit_{product_id}')])
            keyboard.append([InlineKeyboardButton(f"Удалить {name[:20]}", callback_data=f'delete_{product_id}')])

        keyboard.append([InlineKeyboardButton("Назад", callback_data='admin_panel')])

        if len(products) > 10:
            message += f"\nВсего товаров: {len(products)}. Показаны первые 10."

        await query.edit_message_text(
            text=message,
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

        stats_message = "Статистика магазина\n\n"
        stats_message += f"Всего товаров: {len(products)}\n\n"
        stats_message += "По категориям:\n"
        for cat_id, cat_name in CATEGORY_NAMES.items():
            count = stats.get(cat_id, 0)
            stats_message += f"• {cat_name}: {count}\n"

        await query.edit_message_text(
            text=stats_message,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data='admin_panel')]])
        )

    elif query.data == 'cleanup_photos':
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return
        cleanup_orphan_photos()
        await query.edit_message_text(
            "Очистка выполнена. Лишние фото удалены и запушены в GitHub Pages.",
            reply_markup=get_admin_menu()
        )

    elif query.data.startswith('edit_') and not any(query.data.startswith(p) for p in (
        'edit_name_', 'edit_price_', 'edit_category_', 'edit_photos_'
    )):
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return

        product_id = int(query.data.split('_')[1])
        product = get_product_by_id(product_id)

        if not product:
            await query.edit_message_text("Товар не найден!", reply_markup=get_admin_menu())
            return

        photos = json.loads(product[4])

        keyboard = [
            [InlineKeyboardButton("Изменить название", callback_data=f'edit_name_{product_id}')],
            [InlineKeyboardButton("Изменить цену", callback_data=f'edit_price_{product_id}')],
            [InlineKeyboardButton("Изменить категорию", callback_data=f'edit_category_{product_id}')],
            [InlineKeyboardButton("Изменить фото", callback_data=f'edit_photos_{product_id}')],
            [InlineKeyboardButton("Назад", callback_data='list_products')]
        ]

        await query.edit_message_text(
            text=(
                f"Редактирование товара\n\n"
                f"ID: {product[0]}\n"
                f"Название: {product[1]}\n"
                f"Цена: {product[2]} руб.\n"
                f"Категория: {CATEGORY_NAMES.get(product[3], product[3])}\n"
                f"Фото: {len(photos)} шт."
            ),
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
                [InlineKeyboardButton("Да, удалить", callback_data=f'confirm_delete_{product_id}')],
                [InlineKeyboardButton("Нет, отмена", callback_data='list_products')]
            ]

            await query.edit_message_text(
                text=(
                    f"Подтверждение удаления\n\n"
                    f"Вы уверены, что хотите удалить товар?\n\n"
                    f"{product[1]}\n{product[2]} руб."
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif query.data.startswith('confirm_delete_'):
        if user_id != ADMIN_ID:
            await query.answer("У вас нет доступа!", show_alert=True)
            return

        product_id = int(query.data.split('_')[2])
        delete_product(product_id)

        await query.edit_message_text("Товар успешно удален!", reply_markup=get_admin_menu())

    elif query.data.startswith('edit_name_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'name', 'id': product_id}
        await query.edit_message_text("Введите новое название товара:")
        return NAME

    elif query.data.startswith('edit_price_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'price', 'id': product_id}
        await query.edit_message_text("Введите новую цену товара (только число):")
        return PRICE

    elif query.data.startswith('edit_category_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'category', 'id': product_id}
        await query.edit_message_text(
            "Выберите новую категорию:",
            reply_markup=get_category_keyboard()
        )
        return CATEGORY

    elif query.data.startswith('edit_photos_'):
        product_id = int(query.data.split('_')[2])
        context.user_data['edit_field'] = {'type': 'photos', 'id': product_id}
        context.user_data['edit_photos'] = []
        await query.edit_message_text(
            "Отправьте новые фото товара (можно до 5 штук).\nСтарые фото будут заменены."
        )
        return PHOTOS

    elif query.data == 'cancel_add':
        if 'add_product' in context.user_data:
            photos = context.user_data['add_product'].get('photos', [])
            for photo_path in photos:
                if os.path.exists(photo_path):
                    try:
                        os.remove(photo_path)
                    except Exception:
                        pass
            del context.user_data['add_product']
        if 'edit_field' in context.user_data:
            del context.user_data['edit_field']
        if 'edit_photos' in context.user_data:
            for p in context.user_data['edit_photos']:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            del context.user_data['edit_photos']
        await query.edit_message_text("Действие отменено.", reply_markup=get_admin_menu())
        return ConversationHandler.END


# ── Редактирование поля ──────────────────────────────────────────
async def edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field_data = context.user_data.get('edit_field')
    if not field_data:
        await update.message.reply_text("Ошибка! Попробуйте снова.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    product = get_product_by_id(field_data['id'])
    if not product:
        await update.message.reply_text("Товар не найден!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    if field_data['type'] == 'name':
        new_value = update.message.text
        photos = json.loads(product[4])
        update_product(field_data['id'], new_value, product[2], product[3], photos)
        await update.message.reply_text(f"Название изменено на: {new_value}", reply_markup=get_admin_menu())

    elif field_data['type'] == 'price':
        try:
            new_value = int(update.message.text)
            if new_value <= 0:
                raise ValueError
            photos = json.loads(product[4])
            update_product(field_data['id'], product[1], new_value, product[3], photos)
            await update.message.reply_text(f"Цена изменена на: {new_value} руб.", reply_markup=get_admin_menu())
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректное число (больше 0).", reply_markup=get_admin_menu())
            return PRICE

    elif field_data['type'] == 'photos':
        if update.message.photo:
            if 'edit_photos' not in context.user_data:
                context.user_data['edit_photos'] = []

            photo_file = await update.message.photo[-1].get_file()
            timestamp = int(datetime.now().timestamp())
            filename = f"{product[1]}_edit_{len(context.user_data['edit_photos'])+1}_{timestamp}.jpg"
            filename = "".join(c for c in filename if c.isalnum() or c in '._-')
            file_path = f"{PHOTOS_DIR}/{filename}"

            await photo_file.download_to_drive(file_path)
            context.user_data['edit_photos'].append(file_path)

            if len(context.user_data['edit_photos']) >= 5:
                old_photos = json.loads(product[4])
                for old in old_photos:
                    if os.path.exists(old):
                        try:
                            os.remove(old)
                        except Exception:
                            pass
                    gh_old = os.path.join(GH_PAGES_DIR, os.path.basename(old))
                    if os.path.exists(gh_old):
                        try:
                            os.remove(gh_old)
                        except Exception:
                            pass

                update_product(field_data['id'], product[1], product[2], product[3], context.user_data['edit_photos'])

                for ph in context.user_data['edit_photos']:
                    publish_photo_to_pages(ph)
                git_push_pages(f"update photos product #{field_data['id']}")

                with open(context.user_data['edit_photos'][0], 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=f"Фото товара обновлены! Загружено {len(context.user_data['edit_photos'])} фото.",
                        reply_markup=get_admin_menu()
                    )

                del context.user_data['edit_field']
                del context.user_data['edit_photos']
                return ConversationHandler.END
            else:
                keyboard = [
                    [InlineKeyboardButton("Добавить еще фото", callback_data='add_more_edit_photos')],
                    [InlineKeyboardButton("Завершить обновление", callback_data='finish_edit_photos')]
                ]
                await update.message.reply_text(
                    f"Фото {len(context.user_data['edit_photos'])}/5 добавлено.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return PHOTOS
        else:
            await update.message.reply_text(
                "Пожалуйста, отправьте фото.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Завершить обновление", callback_data='finish_edit_photos')]
                ])
            )
            return PHOTOS

    del context.user_data['edit_field']
    return ConversationHandler.END


# ── Завершение обновления фото ───────────────────────────────────
async def finish_edit_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    field_data = context.user_data.get('edit_field')
    if not field_data or field_data.get('type') != 'photos':
        await query.edit_message_text("Ошибка. Попробуйте заново.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    new_photos = context.user_data.get('edit_photos', [])
    if not new_photos:
        await query.edit_message_text("Нужно добавить хотя бы одно фото!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    product = get_product_by_id(field_data['id'])
    if not product:
        await query.edit_message_text("Товар не найден!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    old_photos = json.loads(product[4])
    for old in old_photos:
        if os.path.exists(old):
            try:
                os.remove(old)
            except Exception:
                pass
        gh_old = os.path.join(GH_PAGES_DIR, os.path.basename(old))
        if os.path.exists(gh_old):
            try:
                os.remove(gh_old)
            except Exception:
                pass

    update_product(field_data['id'], product[1], product[2], product[3], new_photos)

    for ph in new_photos:
        publish_photo_to_pages(ph)
    git_push_pages(f"update photos product #{field_data['id']}")

    del context.user_data['edit_field']
    del context.user_data['edit_photos']

    await query.edit_message_text(
        f"Фото обновлены! Загружено {len(new_photos)} фото.",
        reply_markup=get_admin_menu()
    )
    return ConversationHandler.END


async def add_more_edit_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отправьте следующее фото:")
    return PHOTOS


# ── WebApp data (заказы) ─────────────────────────────────────────
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data.data
    logger.info(f"Получены данные из WebApp: {data[:200]}")

    user = update.effective_user

    try:
        request = json.loads(data)

        if request.get('action') == 'order':
            customer = request.get('customer', {})
            order_text = "НОВЫЙ ЗАКАЗ\n\n"
            order_text += f"Клиент: @{user.username if user.username else 'неизвестно'}\n"
            order_text += f"Имя: {customer.get('name') or user.first_name}\n"
            order_text += f"Телефон: {customer.get('phone','—')}\n"
            order_text += f"Адрес: {customer.get('address','—')}\n"
            if customer.get('comment'):
                order_text += f"Комментарий: {customer['comment']}\n"
            order_text += f"ID: {user.id}\n"
            order_text += "\nТовары:\n"

            for item in request.get('cart', []):
                order_text += f"• {item['name']} x{item['quantity']} — {item['price'] * item['quantity']} руб.\n"

            order_text += f"\nДоставка: {request.get('delivery', 0)} руб."
            order_text += f"\nИтого: {request.get('total', 0)} руб."

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
                'items': request.get('cart', []),
                'customer': customer,
                'total': request.get('total', 0)
            }
            orders.append(order_record)

            with open(orders_file, 'w', encoding='utf-8') as f:
                json.dump(orders, f, ensure_ascii=False, indent=2)

            await update.message.reply_text(order_text)

            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"НОВЫЙ ЗАКАЗ!\n\n"
                        f"{customer.get('name') or user.first_name} (@{user.username})\n"
                        f"Телефон: {customer.get('phone','—')}\n"
                        f"Адрес: {customer.get('address','—')}\n"
                        f"Сумма: {request.get('total', 0)} руб.\n"
                        f"Товаров: {len(request.get('cart', []))}"
                    )
                )

            await update.message.reply_text(
                "Заказ оформлен! Наш менеджер свяжется с вами в ближайшее время.",
                reply_markup=get_main_menu(user.id)
            )

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        await update.message.reply_text("Произошла ошибка при обработке данных.")
    except Exception as e:
        logger.error(f"Ошибка обработки данных из WebApp: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса. Попробуйте позже.")


# ── Текст ────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or '').lower()

    if 'канал' in text:
        await update.message.reply_text(
            "Наш канал:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Перейти на канал", url='https://t.me/+ajAM1qe9EBszMmFi')
            ]])
        )
    elif 'отзыв' in text:
        await update.message.reply_text(
            "Отзывы о нас:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Читать отзывы", url='https://t.me/otzivi_kudishop')
            ]])
        )
    elif 'авито' in text:
        await update.message.reply_text(
            "Наш магазин на Авито:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Перейти на Авито", url='https://www.avito.ru/user/14fc9')
            ]])
        )
    else:
        await update.message.reply_text(
            "Используйте кнопки меню или команду /start",
            reply_markup=get_main_menu(user_id)
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")


# ── main ─────────────────────────────────────────────────────────
def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    add_product_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern='^add_product$')],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            CATEGORY: [CallbackQueryHandler(button_callback, pattern='^cat_')],
            PHOTOS: [
                MessageHandler(filters.PHOTO, add_product_photos),
                CallbackQueryHandler(button_callback, pattern='^(add_more_photos|finish_adding_product)$'),
            ],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )

    edit_name_price_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern='^edit_name_'),
            CallbackQueryHandler(button_callback, pattern='^edit_price_'),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_value)],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )

    edit_photos_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern='^edit_photos_')],
        states={
            PHOTOS: [
                MessageHandler(filters.PHOTO, edit_field_value),
                CallbackQueryHandler(add_more_edit_photos_callback, pattern='^add_more_edit_photos$'),
                CallbackQueryHandler(finish_edit_photos_callback, pattern='^finish_edit_photos$'),
            ],
        },
        fallbacks=[CallbackQueryHandler(button_callback, pattern='^cancel_add$')],
        per_message=False,
    )

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
    application.add_handler(edit_name_price_handler)
    application.add_handler(edit_photos_handler)
    application.add_handler(edit_category_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен в режиме long polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
