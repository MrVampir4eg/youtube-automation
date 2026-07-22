"""
Flask Dashboard
Веб-інтерфейс для моніторингу та управління системою
"""

import os
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_cors import CORS
from datetime import datetime, timedelta
import json

from src.orchestrator import VideoProducer
from src.scheduler import AutomationScheduler
from database.models import Database

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')

# Ініціалізація компонентів
producer = VideoProducer()
scheduler = AutomationScheduler()
db = Database()

# Запуск scheduler
scheduler.start()


@app.route('/')
def index():
    """Головна сторінка"""
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    """Загальна статистика"""
    total_stats = db.get_total_stats()
    session_stats = producer.get_session_stats()

    # Топ відео
    top_videos = producer.get_top_performing_videos(limit=5)

    # Денна статистика за 7 днів
    daily_stats = db.get_daily_stats(days=7)

    return jsonify({
        'total': total_stats,
        'session': session_stats,
        'top_videos': [{
            'video_id': v['video_id'],
            'title': v['title'],
            'niche': v['niche'],
            'views': v.get('analytics', {}).get('views', 0),
            'likes': v.get('analytics', {}).get('likes', 0),
            'url': v.get('youtube_url')
        } for v in top_videos],
        'daily_chart': {
            'dates': [s['date'] for s in reversed(daily_stats)],
            'views': [s['total_views'] for s in reversed(daily_stats)],
            'revenue': [s['total_revenue'] for s in reversed(daily_stats)],
            'profit': [s['profit'] for s in reversed(daily_stats)]
        }
    })


@app.route('/api/videos')
def list_videos():
    """Список відео"""
    limit = request.args.get('limit', 50, type=int)
    niche = request.args.get('niche')

    videos = db.list_videos(limit=limit, niche=niche)

    return jsonify({
        'videos': [{
            'video_id': v['video_id'],
            'title': v['title'],
            'niche': v['niche'],
            'duration': v['duration'],
            'youtube_url': v.get('youtube_url'),
            'created_at': v['created_at'],
            'ai_cost': v.get('ai_cost', 0)
        } for v in videos]
    })


@app.route('/api/video/<video_id>')
def get_video(video_id):
    """Детальна інформація про відео"""
    performance = producer.get_video_performance(video_id)

    if 'error' in performance:
        return jsonify({'error': performance['error']}), 404

    return jsonify(performance)


@app.route('/api/generate', methods=['POST'])
def generate_video():
    """Ручна генерація відео"""
    data = request.json or {}
    niche = data.get('niche')
    count = data.get('count', 1)

    try:
        results = scheduler.trigger_manual_generation(count=count, niche=niche)

        return jsonify({
            'success': True,
            'videos': [{
                'video_id': r['video_id'],
                'title': r['title'],
                'url': r.get('youtube_url')
            } for r in results if 'error' not in r]
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/schedule')
def get_schedule():
    """Розклад наступних запусків"""
    schedule = scheduler.get_next_run_times()

    return jsonify({
        'is_running': scheduler.is_running,
        'jobs': schedule,
        'config': {
            'videos_per_day': scheduler.videos_per_day,
            'generation_time': scheduler.generation_time,
            'timezone': str(scheduler.timezone)
        }
    })


@app.route('/api/niches')
def get_niches():
    """Список ніш"""
    niches = producer.content_gen.niches

    return jsonify({
        'niches': [{
            'id': niche_id,
            'name': niche['name'],
            'description': niche['description'],
            'target_cpm': niche['target_cpm']
        } for niche_id, niche in niches.items()]
    })


@app.route('/api/analytics/refresh', methods=['POST'])
def refresh_analytics():
    """Оновити аналітику"""
    try:
        scheduler.update_analytics()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'scheduler_running': scheduler.is_running,
        'timestamp': datetime.utcnow().isoformat()
    })


if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

    print("\n" + "="*60)
    print("YouTube Shorts Automation Dashboard")
    print("="*60)
    print(f"\n🌐 Starting server on http://localhost:{port}")
    print(f"📊 Dashboard: http://localhost:{port}")
    print(f"🔧 API Docs: http://localhost:{port}/health")
    print("\n" + "="*60 + "\n")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
