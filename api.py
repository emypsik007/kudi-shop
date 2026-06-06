from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
import json
import os

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с GitHub Pages

# URL для доступа к фото (нужно настроить ваш сервер для раздачи статики)
# Если бот и API на одном сервере, можно использовать относительные пути
# Для продакшена лучше загружать фото на Imgur или другой хостинг
PHOTO_BASE_URL = "https://emypsik007.github.io/kudi-shop/product_photos/"  # Замените на ваш URL

def get_products():
    """Получение всех товаров из базы данных"""
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    try:
        # Проверяем существование таблицы и колонок
        cursor.execute("PRAGMA table_info(products)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Если есть колонка image_url, используем её, иначе photos
        if 'image_url' in columns:
            cursor.execute('SELECT id, name, price, category, image_url FROM products ORDER BY id DESC')
            products = cursor.fetchall()
            conn.close()
            return [{
                'id': p[0],
                'name': p[1],
                'price': p[2],
                'category': p[3],
                'photos': [p[4]] if p[4] else [],
                'main_photo': p[4]
            } for p in products if p[1] is not None]
        else:
            # Используем поле photos (JSON массив)
            cursor.execute('SELECT id, name, price, category, photos FROM products ORDER BY id DESC')
            products = cursor.fetchall()
            conn.close()
            
            result = []
            for p in products:
                if p[1] is None:  # Пропускаем товары без названия
                    continue
                photos = []
                if p[4]:
                    try:
                        photos_list = json.loads(p[4])
                        # Преобразуем локальные пути в URL
                        for photo in photos_list:
                            if photo.startswith('product_photos/'):
                                photos.append(PHOTO_BASE_URL + os.path.basename(photo))
                            else:
                                photos.append(photo)
                    except:
                        pass
                
                result.append({
                    'id': p[0],
                    'name': p[1],
                    'price': p[2],
                    'category': p[3],
                    'photos': photos,
                    'main_photo': photos[0] if photos else None
                })
            return result
    except Exception as e:
        print(f"Ошибка при получении товаров: {e}")
        conn.close()
        return []

@app.route('/api/products')
def products():
    return jsonify(get_products())

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
