import os
import time
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from threading import Thread
import requests
import pandas as pd
from io import BytesIO

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

# Генерация ответа
def generate_response(name, rating, pros, cons):
    if rating == 5 and not cons:
        return f"{name}, спасибо за 5 звёзд! 💜\n\nОчень рады что вам понравилось! Носите с удовольствием! ✨\n\nС любовью, Lavanda Sky 💜"
    elif cons:
        return f"{name}, спасибо за отзыв! 💜\n\nЖаль что {cons.lower()} Будем рады видеть вас снова!\n\nС любовью, Lavanda Sky 💜"
    else:
        return f"{name}, спасибо за отзыв! 💜\n\nОчень рады что товар вам понравился!\n\nС любовью, Lavanda Sky 💜"

# HTML шаблон с загрузкой Excel
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Панель управления отзывами WB</title>
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
            text-align: center;
        }
        h1 { color: #667eea; }
        .upload-area {
            background: white;
            padding: 40px;
            border-radius: 15px;
            margin-bottom: 20px;
            text-align: center;
        }
        .upload-box {
            border: 3px dashed #667eea;
            padding: 40px;
            border-radius: 10px;
            cursor: pointer;
        }
        input[type="file"] { display: none; }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            margin: 10px;
        }
        button:hover { opacity: 0.8; }
        button:disabled { opacity: 0.5; }
        .review-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .response-box {
            background: #f0f7ff;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }
        .alert-success { background: #d4edda; color: #155724; }
        .alert-error { background: #f8d7da; color: #721c24; }
        .timer {
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-weight: 600;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Панель управления отзывами WB</h1>
            <p>Загрузите Excel → Сгенерируйте ответы → Опубликуйте</p>
        </div>
        
        <div class="upload-area">
            <div class="upload-box">
                <h2 style="color: #667eea;">📂 Загрузите Excel файл</h2>
                <input type="file" id="fileInput" accept=".xlsx,.xls" />
                <button onclick="document.getElementById('fileInput').click()">
                    Выбрать файл
                </button>
            </div>
        </div>
        
        <div id="results"></div>
    </div>
    
    <script>
        document.getElementById('fileInput').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            const formData = new FormData();
            formData.append('file', file);
            
            document.getElementById('results').innerHTML = '<div class="alert alert-success">Загружаем...</div>';
            
            try {
                const response = await fetch('/upload-excel', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayReviews(data.reviews);
                } else {
                    document.getElementById('results').innerHTML = 
                        '<div class="alert alert-error">Ошибка: ' + data.error + '</div>';
                }
            } catch (error) {
                document.getElementById('results').innerHTML = 
                    '<div class="alert alert-error">Ошибка загрузки: ' + error.message + '</div>';
            }
        });
        
        function displayReviews(reviews) {
            const html = reviews.map((r, i) => `
                <div class="review-card">
                    <h3>Отзыв ${i+1}: ${r.name} (${'⭐'.repeat(r.rating)})</h3>
                    ${r.text ? '<p><strong>Текст:</strong> ' + r.text + '</p>' : ''}
                    ${r.pros ? '<p><strong>✅ Плюсы:</strong> ' + r.pros + '</p>' : ''}
                    ${r.cons ? '<p><strong>❌ Минусы:</strong> ' + r.cons + '</p>' : ''}
                    <div class="response-box">
                        <strong>Ответ:</strong>
                        <p>${r.response}</p>
                    </div>
                    <div id="status-${i}"></div>
                </div>
            `).join('') + `
                <div class="review-card">
                    <button onclick="publishAll()" id="publishBtn" style="width: 100%; font-size: 18px;">
                        🚀 Опубликовать все (пауза 60 сек между публикациями)
                    </button>
                </div>
            `;
            
            document.getElementById('results').innerHTML = html;
            window.reviewsData = reviews;
        }
        
        async function publishAll() {
            const btn = document.getElementById('publishBtn');
            btn.disabled = true;
            
            for (let i = 0; i < window.reviewsData.length; i++) {
                const review = window.reviewsData[i];
                const statusDiv = document.getElementById('status-' + i);
                
                statusDiv.innerHTML = '<p style="color: #667eea;">⏳ Публикуем...</p>';
                
                try {
                    const response = await fetch('/publish-review', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(review)
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        statusDiv.innerHTML = '<div class="alert alert-success">✅ ОПУБЛИКОВАНО!</div>';
                    } else {
                        statusDiv.innerHTML = '<div class="alert alert-error">❌ Ошибка: ' + data.error + '</div>';
                    }
                } catch (error) {
                    statusDiv.innerHTML = '<div class="alert alert-error">❌ Ошибка: ' + error.message + '</div>';
                }
                
                // Пауза 60 секунд
                if (i < window.reviewsData.length - 1) {
                    for (let sec = 60; sec > 0; sec--) {
                        statusDiv.innerHTML += '<div class="timer">⏰ Следующая через: ' + sec + ' сек</div>';
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        const timers = statusDiv.querySelectorAll('.timer');
                        if (timers.length > 0) timers[timers.length - 1].remove();
                    }
                }
            }
            
            btn.textContent = '✅ Публикация завершена';
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload-excel', methods=['POST'])
def upload_excel():
    try:
        file = request.files['file']
        df = pd.read_excel(BytesIO(file.read()))
        
        reviews = []
        for _, row in df.iterrows():
            review = {
                'id': row['ID отзыва'],
                'name': row['Имя'] if pd.notna(row['Имя']) else 'Милая',
                'rating': int(row['Количество звезд']) if pd.notna(row['Количество звезд']) else 5,
                'text': row['Текст отзыва'] if pd.notna(row['Текст отзыва']) else '',
                'pros': row['Достоинства'] if pd.notna(row['Достоинства']) else '',
                'cons': row['Недостатки'] if pd.notna(row['Недостатки']) else '',
            }
            review['response'] = generate_response(
                review['name'], 
                review['rating'], 
                review['pros'], 
                review['cons']
            )
            reviews.append(review)
        
        return jsonify({'success': True, 'reviews': reviews})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/publish-review', methods=['POST'])
def publish_review():
    try:
        data = request.json
        
        response = requests.post(
            f'{WB_API_BASE}/api/v1/feedbacks/answer',
            headers={
                'Authorization': WB_API_TOKEN,
                'Content-Type': 'application/json'
            },
            json={
                'id': data['id'],
                'text': data['response']
            },
            timeout=10
        )
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'WB API error: {response.status_code}'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
