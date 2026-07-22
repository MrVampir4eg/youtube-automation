"""
Flask Dashboard
Веб-інтерфейс для моніторингу та управління системою
"""

import os
import uuid
from threading import Lock, Thread
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

# Ручна генерація виконується у фоні, щоб Render не обривав
# довгий HTTP-запит під час рендерингу.
generation_jobs = {}
generation_jobs_lock = Lock()
generation_worker_lock = Lock()


def _update_generation_job(job_id, **updates):
    with generation_jobs_lock:
        generation_jobs[job_id].update(updates)


def _run_generation_job(job_id, count, niche):
    """Фонова генерація одного завдання за раз."""
    with generation_worker_lock:
        _update_generation_job(
            job_id,
            status='running',
            started_at=datetime.utcnow().isoformat()
        )

        try:
            results = scheduler.trigger_manual_generation(count=count, niche=niche)
            videos = [{
                'video_id': result['video_id'],
                'title': result['title'],
                'url': result.get('youtube_url')
            } for result in results if 'error' not in result]

            errors = [result['error'] for result in results if 'error' in result]
            if not videos:
                raise RuntimeError('; '.join(errors) or 'Відео не створено')

            _update_generation_job(
                job_id,
                status='completed',
                videos=videos,
                completed_at=datetime.utcnow().isoformat()
            )
        except Exception as exc:
            _update_generation_job(
                job_id,
                status='failed',
                error=str(exc),
                completed_at=datetime.utcnow().isoformat()
            )


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
    """Запустити фонову генерацію відео."""
    data = request.get_json(silent=True) or {}
    niche = data.get('niche')
    count = max(1, min(int(data.get('count', 1)), 1))

    with generation_jobs_lock:
        active_job = next((
            existing_id for existing_id, job in generation_jobs.items()
            if job['status'] in ('queued', 'running')
        ), None)

        if active_job:
            return jsonify({
                'success': False,
                'error': 'Інше відео вже генерується',
                'job_id': active_job
            }), 409

        job_id = uuid.uuid4().hex[:12]
        generation_jobs[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'created_at': datetime.utcnow().isoformat(),
            'videos': []
        }

    Thread(
        target=_run_generation_job,
        args=(job_id, count, niche),
        daemon=True
    ).start()

    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': 'queued'
    }), 202


@app.route('/api/generate/<job_id>')
def generation_status(job_id):
    """Стан фонової генерації."""
    with generation_jobs_lock:
        job = generation_jobs.get(job_id)
        if not job:
            return jsonify({
                'success': False,
                'error': 'Завдання не знайдено; можливо, сервіс перезапустився'
            }), 404
        return jsonify({'success': True, **job})


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
    # Render/Railway передають порт у PORT. FLASK_PORT лишається
    # резервним варіантом для локального запуску.
    port = int(os.getenv('PORT', os.getenv('FLASK_PORT', 5000)))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

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
