import os
import time
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from threading import Thread
import requests

app = Flask(__name__)

# Конфигурация
WB_API_TOKEN = os.environ.get('WB_API_TOKEN', '')
WB_API_BASE = 'https://feedbacks-api.wildberries.ru'
CHECK_INTERVAL = 600  # 10 минут

# База данных
def init_db():
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id TEXT PRIMARY KEY, 
                  data TEXT, 
                  response TEXT,
                  published INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Проверка новых отзывов
def check_new_reviews():
    try:
        print(f"[{datetime.now()}] Проверка новых отзывов...")
        
        response = requests.get(
            f"{WB_API_BASE}/api/v1/feedbacks",
            params={'isAnswered': 'false', 'take': 50},
            headers={'Authorization': WB_API_TOKEN}
        )
        
        if response.status_code == 200:
            data = response.json()
            reviews = data.get('data', {}).get('feedbacks', [])
            
            conn = sqlite3.connect('reviews.db')
            c = conn.cursor()
            
            new_count = 0
            for review in reviews:
                review_id = review.get('id')
                c.execute('SELECT id FROM reviews WHERE id = ?', (review_id,))
                if not c.fetchone():
                    c.execute('INSERT INTO reviews (id, data) VALUES (?, ?)',
                             (review_id, json.dumps(review, ensure_ascii=False)))
                    new_count += 1
            
            conn.commit()
            conn.close()
            
            print(f"[{datetime.now()}] Найдено новых отзывов: {new_count}")
        else:
            print(f"[{datetime.now()}] Ошибка API: {response.status_code}")
            
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка: {e}")

# Фоновая задача
def background_checker():
    while True:
        check_new_reviews()
        time.sleep(CHECK_INTERVAL)

# HTML шаблон
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lavanda Sky - Панель отзывов (Серверная)</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
        }
        h1 { color: #667eea; }
        .info-box {
            background: #d4edda;
            border: 2px solid #28a745;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .review-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .review-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }
        .badge {
            padding: 5px 10px;
            border-radius: 10px;
            font-size: 12px;
            margin-right: 5px;
        }
        .badge-new { background: #fff3cd; }
        .badge-photo { background: #d4edda; }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            margin: 5px;
        }
        button:hover { opacity: 0.8; }
        .btn-success { background: #28a745; }
        .response-box {
            background: #f0f7ff;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Серверная панель</h1>
            <p>Автопроверка каждые 10 минут • Без лимитов при просмотре</p>
        </div>
        
        <div class="info-box">
            <strong>✅ Сервер работает!</strong><br>
            Последняя проверка: <span id="lastCheck">загрузка...</span><br>
            Необработанных отзывов: <span id="count">загрузка...</span>
        </div>
        
        <button onclick="loadReviews()">🔄 Обновить список</button>
        
        <div id="reviews"></div>
    </div>
    
    <script>
        async function loadReviews() {
            const response = await fetch('/api/reviews');
            const data = await response.json();
            
            document.getElementById('count').textContent = data.reviews.length;
            document.getElementById('lastCheck').textContent = new Date().toLocaleString('ru-RU');
            
            const container = document.getElementById('reviews');
            if (data.reviews.length === 0) {
                container.innerHTML = '<div class="review-card"><h3>🎉 Нет новых отзывов!</h3></div>';
                return;
            }
            
            container.innerHTML = data.reviews.map(r => {
                const review = JSON.parse(r.data);
                return `
                    <div class="review-card">
                        <div class="review-header">
                            <div>
                                <span class="badge badge-new">НОВЫЙ</span>
                                ${review.photoLinks?.length ? '<span class="badge badge-photo">📸</span>' : ''}
                                <div style="margin-top: 10px;">
                                    <strong>${review.userName || 'Имя не указано'}</strong> • 
                                    ${'⭐'.repeat(review.productValuation)}
                                </div>
                            </div>
                        </div>
                        <p>${review.text || '<i>Текст не оставлен</i>'}</p>
                        <div id="resp-${r.id}"></div>
                        <button onclick="generate('${r.id}', ${JSON.stringify(review).replace(/"/g, '&quot;')})">
                            ✨ Сгенерировать ответ
                        </button>
                    </div>
                `;
            }).join('');
        }
        
        async function generate(id, review) {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id, review})
            });
            const data = await response.json();
            
            document.getElementById('resp-' + id).innerHTML = `
                <div class="response-box">
                    <strong>Ответ:</strong>
                    <p>${data.response}</p>
                    <button class="btn-success" onclick="publish('${id}', '${data.response.replace(/'/g, "\\'")}')">
                        ✅ Опубликовать
                    </button>
                </div>
            `;
        }
        
        async function publish(id, text) {
            await fetch('/api/publish', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id, text})
            });
            alert('✅ Опубликовано!');
            loadReviews();
        }
        
        loadReviews();
        setInterval(loadReviews, 60000); // Обновляем каждую минуту
    </script>
</body>
</html>
'''

# API endpoints
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/reviews')
def get_reviews():
    conn = sqlite3.connect('reviews.db')
    c = conn.cursor()
    c.execute('SELECT id, data FROM reviews WHERE published = 0 ORDER BY created_at DESC')
    reviews = [{'id': row[0], 'data': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify({'reviews': reviews})

@app.route('/api/generate', methods=['POST'])
def generate_response():
    data = request.json
    review = data['review']
    
    # Простой шаблон ответа (здесь можно подключить Claude API)
    response_text = f"{review.get('userName', 'Милая')}, спасибо за отзыв! 💜\n\nОчень рады что вам понравилось!\n\nС любовью, Lavanda Sky 💜"
    
    return jsonify({'response': response_text})

@app.route('/api/publish', methods=['POST'])
def publish_response():
    data = request.json
    review_id = data['id']
    response_text = data['text']
    
    try:
        # Публикуем на WB
        response = requests.post(
            f"{WB_API_BASE}/api/v1/feedbacks/answer",
            headers={
                'Authorization': WB_API_TOKEN,
                'Content-Type': 'application/json'
            },
            json={'id': review_id, 'text': response_text}
        )
        
        if response.status_code == 200:
            # Отмечаем как опубликованный
            conn = sqlite3.connect('reviews.db')
            c = conn.cursor()
            c.execute('UPDATE reviews SET published = 1, response = ? WHERE id = ?',
                     (response_text, review_id))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    init_db()
    
    # Запускаем фоновую проверку
    checker_thread = Thread(target=background_checker, daemon=True)
    checker_thread.start()
    
    # Запускаем веб-сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
