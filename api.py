from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с GitHub Pages

def get_products():
    conn = sqlite3.connect('products.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, category, image_url FROM products')
    products = cursor.fetchall()
    conn.close()
    
    return [{
        'id': p[0], 
        'name': p[1], 
        'price': p[2], 
        'category': p[3], 
        'image': p[4]
    } for p in products]

@app.route('/api/products')
def products():
    return jsonify(get_products())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)