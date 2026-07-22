"""
Flask Dashboard
Веб-інтерфейс для моніторингу та управління системою
"""

import os
import secrets
import uuid
from pathlib import Path
from threading import Lock, Thread
from flask import (
    Flask, render_template, jsonify, request, redirect, url_for,
    send_file, session, make_response, flash, g
)
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlparse
from google_auth_oauthlib.flow import Flow
from werkzeug.middleware.proxy_fix import ProxyFix

from src.orchestrator import VideoProducer
from src.scheduler import AutomationScheduler
from src.youtube_uploader import SCOPES, YouTubeUploader
from src.platform_publishers import is_valid_media_signature
from src.admin_security import AdminSecurity
from database.models import Database

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
# Один process-level secret підписує тимчасові MP4 URL для Instagram. На Render
# краще задати MEDIA_SHARE_SECRET, але без нього поточний instance теж працює.
os.environ.setdefault('MEDIA_SHARE_SECRET', str(app.secret_key))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('RENDER', 'False').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_REFRESH_EACH_REQUEST=True,
)
project_root = Path(__file__).resolve().parents[1]
video_output_dir = (project_root / 'output' / 'videos').resolve()

# Ініціалізація компонентів. Dashboard і scheduler використовують один
# producer, тому OAuth/профілі не розходяться між двома копіями стану.
scheduler = AutomationScheduler()
producer = scheduler.producer
db = Database()
admin_security = AdminSecurity(db)
admin_bootstrap_error = None
try:
    admin_security.bootstrap_from_environment()
except ValueError as exc:
    # A weak/invalid bootstrap password should not crash Render health checks;
    # login clearly shows that the administrator is not configured.
    admin_bootstrap_error = str(exc)
    app.logger.error("Admin bootstrap failed: %s", exc)

# Запуск scheduler
scheduler.start()

# Ручна генерація виконується у фоні, щоб Render не обривав
# довгий HTTP-запит під час рендерингу.
generation_jobs = {}
generation_jobs_lock = Lock()
generation_worker_lock = Lock()
login_attempts = {}
login_attempts_lock = Lock()


@app.context_processor
def inject_security_status():
    return {'admin_bootstrap_error': admin_bootstrap_error}


def _client_ip():
    return (request.remote_addr or 'unknown')[:100]


def _csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def _valid_csrf():
    submitted = (
        request.headers.get('X-CSRF-Token')
        or request.form.get('csrf_token')
        or ''
    )
    expected = session.get('csrf_token') or ''
    return bool(expected and secrets.compare_digest(expected, submitted))


def _is_automation_bot():
    expected = os.getenv('AUTOMATION_API_TOKEN', '').strip()
    header = request.headers.get('Authorization', '')
    if not expected or not header.startswith('Bearer '):
        return False
    return secrets.compare_digest(expected, header[7:].strip())


def _rate_limited(bucket, limit=5, window_minutes=15):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    with login_attempts_lock:
        recent = [stamp for stamp in login_attempts.get(bucket, []) if stamp > cutoff]
        login_attempts[bucket] = recent
        return len(recent) >= limit


def _record_failed_attempt(bucket):
    with login_attempts_lock:
        login_attempts.setdefault(bucket, []).append(datetime.now(timezone.utc))


def _clear_attempts(bucket):
    with login_attempts_lock:
        login_attempts.pop(bucket, None)


PUBLIC_ENDPOINTS = {
    'login', 'forgot_password', 'reset_password', 'health',
    'share_video_for_platform', 'static'
}
BOT_ENDPOINTS = {'generate_video', 'generation_status', 'bot_status', 'health'}


@app.before_request
def require_admin_and_csrf():
    """Keep the whole control plane private; signed media remains public."""
    endpoint = request.endpoint
    g.automation_bot = bool(endpoint in BOT_ENDPOINTS and _is_automation_bot())

    if endpoint in PUBLIC_ENDPOINTS or g.automation_bot:
        return None

    admin = db.get_admin()
    valid_session = bool(
        session.get('admin_id') == 1
        and admin
        and session.get('admin_password_version') == admin.get('updated_at')
    )
    if not valid_session:
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Потрібен вхід адміністратора'}), 401
        return redirect(url_for('login', next=request.full_path.rstrip('?')))

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not _valid_csrf():
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'CSRF перевірка не пройдена'}), 403
        return 'CSRF перевірка не пройдена', 403
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.endpoint not in {'share_video_for_platform', 'health'}:
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


def _update_generation_job(job_id, **updates):
    with generation_jobs_lock:
        generation_jobs[job_id].update(updates)


def _run_generation_job(
    job_id,
    count,
    niche,
    content_mode,
    profile_id,
    affiliate_offer_id,
    publish_scope,
    trigger_source,
):
    """Фонова генерація одного завдання за раз."""
    with generation_worker_lock:
        _update_generation_job(
            job_id,
            status='running',
            started_at=datetime.utcnow().isoformat()
        )

        try:
            results = scheduler.trigger_manual_generation(
                count=count,
                niche=niche,
                content_mode=content_mode,
                profile_id=profile_id,
                affiliate_offer_id=affiliate_offer_id,
                publish_scope=publish_scope,
                trigger_source=trigger_source,
            )
            videos = [{
                'video_id': result['video_id'],
                'title': result['title'],
                'url': result.get('youtube_url'),
                'upload_error': result.get('youtube_error'),
                'platform_results': result.get('platform_results', {}),
                'content_mode': result.get('content_mode', 'organic'),
                'profile_id': result.get('profile_id', 'default'),
                'profile_name': result.get('profile_name'),
                'affiliate_offer_id': result.get('affiliate_offer_id'),
                'download_url': f"/api/videos/{result['video_id']}/download"
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
            db.finish_automation_run(job_id, 'completed', f'{len(videos)} video(s)')
        except Exception as exc:
            _update_generation_job(
                job_id,
                status='failed',
                error=str(exc),
                completed_at=datetime.utcnow().isoformat()
            )
            db.finish_automation_run(job_id, 'failed', str(exc))


@app.route('/login', methods=['GET', 'POST'])
def login():
    current_admin = db.get_admin()
    if (
        session.get('admin_id') == 1
        and current_admin
        and session.get('admin_password_version') == current_admin.get('updated_at')
    ):
        return redirect(url_for('index'))

    admin_ready = bool(current_admin)
    if request.method == 'POST':
        if not _valid_csrf():
            return render_template(
                'login.html', csrf_token=_csrf_token(), admin_ready=admin_ready,
                error='Сторінка застаріла. Оновіть її та повторіть.'
            ), 403
        bucket = f"login:{_client_ip()}"
        if _rate_limited(bucket):
            return render_template(
                'login.html', csrf_token=_csrf_token(), admin_ready=admin_ready,
                error='Забагато спроб. Зачекайте 15 хвилин.'
            ), 429
        admin = admin_security.authenticate(
            request.form.get('email', ''), request.form.get('password', '')
        )
        if not admin:
            _record_failed_attempt(bucket)
            db.log_audit('login_failed', ip_address=_client_ip())
            return render_template(
                'login.html', csrf_token=_csrf_token(), admin_ready=admin_ready,
                error='Неправильний email або пароль'
            ), 401

        _clear_attempts(bucket)
        session.clear()
        session.permanent = True
        session['admin_id'] = 1
        session['admin_password_version'] = admin['updated_at']
        session['csrf_token'] = secrets.token_urlsafe(32)
        db.log_audit('login_success', ip_address=_client_ip(), admin_id=1)
        target = request.args.get('next', '')
        if not target.startswith('/') or target.startswith('//'):
            target = url_for('index')
        return redirect(target)

    return render_template(
        'login.html', csrf_token=_csrf_token(), admin_ready=admin_ready
    )


@app.route('/logout', methods=['POST'])
def logout():
    db.log_audit('logout', ip_address=_client_ip(), admin_id=1)
    session.clear()
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    sent = False
    error = None
    if request.method == 'POST':
        if not _valid_csrf():
            error = 'Сторінка застаріла. Оновіть її та повторіть.'
        else:
            bucket = f"reset:{_client_ip()}"
            if _rate_limited(bucket, limit=3, window_minutes=30):
                error = 'Забагато запитів. Спробуйте пізніше.'
            else:
                _record_failed_attempt(bucket)
                email = request.form.get('email', '').strip().lower()
                base_url = (
                    os.getenv('PUBLIC_BASE_URL', '').strip()
                    or request.url_root.rstrip('/')
                )
                link = admin_security.create_reset_link(email, base_url)
                if link:
                    try:
                        admin_security.send_reset_email(email, link)
                        db.log_audit('password_reset_email_sent', ip_address=_client_ip())
                    except Exception as exc:
                        app.logger.error('Password reset email failed: %s', exc)
                        db.log_audit(
                            'password_reset_email_failed',
                            {'error_type': type(exc).__name__},
                            _client_ip(),
                        )
                sent = True
    return render_template(
        'forgot_password.html', csrf_token=_csrf_token(), sent=sent, error=error
    )


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    valid = admin_security.validate_reset_token(token)
    error = None
    if request.method == 'POST' and valid:
        if not _valid_csrf():
            error = 'Сторінка застаріла. Оновіть її та повторіть.'
        else:
            password = request.form.get('password', '')
            confirmation = request.form.get('password_confirm', '')
            if password != confirmation:
                error = 'Паролі не збігаються'
            else:
                try:
                    admin_security.reset_password(token, password)
                    db.log_audit('password_reset_completed', ip_address=_client_ip())
                    flash('Пароль змінено. Тепер увійдіть.', 'success')
                    return redirect(url_for('login'))
                except ValueError as exc:
                    error = str(exc)
    return render_template(
        'reset_password.html', csrf_token=_csrf_token(), valid=valid, error=error
    ), (200 if valid else 400)


@app.route('/admin/security', methods=['GET', 'POST'])
def admin_security_page():
    error = None
    success = None
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        if new_password != request.form.get('new_password_confirm', ''):
            error = 'Нові паролі не збігаються'
        else:
            try:
                admin_security.change_password(
                    request.form.get('current_password', ''), new_password
                )
                db.log_audit(
                    'password_changed', ip_address=_client_ip(), admin_id=1
                )
                session['admin_password_version'] = db.get_admin()['updated_at']
                success = 'Пароль змінено. Інші reset-посилання анульовано.'
            except ValueError as exc:
                error = str(exc)
    return render_template(
        'admin_security.html',
        csrf_token=_csrf_token(),
        admin=db.get_admin(),
        smtp_configured=admin_security.smtp_configured(),
        bot_configured=bool(os.getenv('AUTOMATION_API_TOKEN')),
        session_secret_configured=bool(os.getenv('SECRET_KEY')),
        audit=db.list_audit(30),
        bot_runs=db.list_automation_runs(20),
        error=error,
        success=success,
    )


@app.route('/')
def index():
    """Головна сторінка"""
    return render_template(
        'index.html', csrf_token=_csrf_token(), admin=db.get_admin()
    )


@app.route('/youtube/connect')
def youtube_connect():
    """Почати Google OAuth для YouTube-каналу."""
    profile_id = request.args.get('profile_id', 'default').strip()
    profile = db.get_channel_profile(profile_id)
    if not profile:
        return jsonify({'success': False, 'error': 'Профіль каналу не знайдено'}), 404
    uploader = YouTubeUploader(use_token_file=False)
    try:
        # Prefer the exact callback configured in Render. Building it from the
        # incoming proxy request can produce a host that Google has not whitelisted.
        redirect_uri = (
            os.getenv('YOUTUBE_REDIRECT_URI', '').strip()
            or url_for('oauth2callback', _external=True, _scheme='https')
        )
        flow = Flow.from_client_config(
            uploader.get_oauth_client_config(),
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            # select_account is essential when several YouTube channels use the
            # same dashboard; consent requests a durable refresh token.
            prompt='consent select_account'
        )
        session['youtube_oauth_state'] = state
        session['youtube_redirect_uri'] = redirect_uri
        session['youtube_profile_id'] = profile_id
        return redirect(authorization_url)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400


@app.route('/oauth2callback')
def oauth2callback():
    """Прийняти Google OAuth callback і видати refresh token власнику."""
    if request.args.get('error'):
        return jsonify({
            'success': False,
            'error': request.args.get('error_description') or request.args['error']
        }), 400

    state = session.pop('youtube_oauth_state', None)
    redirect_uri = session.pop(
        'youtube_redirect_uri',
        os.getenv('YOUTUBE_REDIRECT_URI', '').strip()
        or url_for('oauth2callback', _external=True, _scheme='https')
    )
    if not state:
        return jsonify({
            'success': False,
            'error': 'OAuth session expired. Open /youtube/connect again.'
        }), 400

    profile_id = session.pop('youtube_profile_id', 'default')
    profile = db.get_channel_profile(profile_id)
    if not profile:
        return jsonify({'success': False, 'error': 'Профіль каналу не знайдено'}), 404
    uploader = YouTubeUploader(use_token_file=False)
    try:
        flow = Flow.from_client_config(
            uploader.get_oauth_client_config(),
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        if not credentials.refresh_token:
            raise RuntimeError(
                'Google did not return a refresh token. Revoke app access and connect again.'
            )

        # Кожен профіль зберігає власний refresh token. Він ніколи не
        # повертається через JSON API або на Dashboard.
        uploader.set_credentials(credentials)
        channel_info = uploader.get_channel_info()
        db.save_channel_credentials(
            profile_id,
            credentials.refresh_token,
            channel_info,
        )
        db.log_audit(
            'youtube_channel_connected',
            {
                'profile_id': profile_id,
                'channel_id': channel_info.get('channel_id'),
            },
            _client_ip(),
            1,
        )
        os.environ['AUTO_UPLOAD'] = 'True'

        response = make_response(render_template(
            'youtube_connected.html',
            profile_name=profile['name'],
            channel_title=channel_info.get('title'),
            channel_id=channel_info.get('channel_id'),
        ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        return response
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400


@app.route('/api/youtube/status')
def youtube_status():
    """Стан YouTube OAuth і автозавантаження."""
    profile_id = request.args.get('profile_id', 'default').strip()
    profile = db.get_channel_profile(profile_id)
    return jsonify({
        'success': True,
        'profile_id': profile_id,
        'connected': bool(profile and profile.get('connected')),
        'auto_upload': os.getenv('AUTO_UPLOAD', 'False').lower() == 'true'
    })


@app.route('/api/platforms/status')
def platforms_status():
    """Єдина перевірка всіх каналів публікації для Dashboard."""
    return jsonify({'success': True, **scheduler.producer.publisher.get_status()})


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
            'platform_results': v.get('platform_results', {}),
            'content_mode': v.get('content_mode', 'organic'),
            'profile_id': v.get('profile_id', 'default'),
            'affiliate_offer_id': v.get('affiliate_offer_id'),
            'created_at': v['created_at'],
            'ai_cost': v.get('ai_cost', 0),
            'download_url': f"/api/videos/{v['video_id']}/download"
        } for v in videos]
    })


@app.route('/api/video/<video_id>')
def get_video(video_id):
    """Детальна інформація про відео"""
    performance = producer.get_video_performance(video_id)

    if 'error' in performance:
        return jsonify({'error': performance['error']}), 404

    return jsonify(performance)


@app.route('/api/videos/<video_id>/download')
def download_video(video_id):
    """Завантажити згенерований MP4 з поточного Render instance."""
    video = db.get_video(video_id)
    if not video or not video.get('video_path'):
        return jsonify({'success': False, 'error': 'Відео не знайдено'}), 404

    stored_path = Path(video['video_path'])
    video_path = (
        stored_path.resolve()
        if stored_path.is_absolute()
        else (project_root / stored_path).resolve()
    )

    if video_output_dir not in video_path.parents or not video_path.is_file():
        return jsonify({
            'success': False,
            'error': 'Файл більше немає на Render. Згенеруйте відео повторно.'
        }), 404

    return send_file(
        video_path,
        mimetype='video/mp4',
        as_attachment=True,
        download_name=f'{video_id}.mp4',
        conditional=True
    )


@app.route('/api/media/<video_id>/<signature>.mp4')
def share_video_for_platform(video_id, signature):
    """Signed short-lived-by-storage URL from which Instagram fetches a Reel."""
    if not video_id.isalnum() or not is_valid_media_signature(video_id, signature):
        return jsonify({'success': False, 'error': 'Недійсне посилання'}), 403

    video_path = (video_output_dir / f'{video_id}.mp4').resolve()
    if video_output_dir not in video_path.parents or not video_path.is_file():
        return jsonify({'success': False, 'error': 'MP4 не знайдено'}), 404

    response = send_file(
        video_path,
        mimetype='video/mp4',
        as_attachment=False,
        conditional=True,
    )
    response.headers['Cache-Control'] = 'private, max-age=600'
    return response


@app.route('/api/generate', methods=['POST'])
def generate_video():
    """Запустити фонову генерацію відео."""
    data = request.get_json(silent=True) or {}
    niche = data.get('niche')
    count = max(1, min(int(data.get('count', 1)), 1))
    content_mode = str(data.get('content_mode', 'organic')).strip().lower()
    profile_id = str(data.get('profile_id', 'default')).strip()
    affiliate_offer_id = data.get('affiliate_offer_id') or None
    trigger_source = 'official_api_bot' if g.automation_bot else 'manual_admin'
    # Existing scheduled calls do not send this field and keep the old
    # universal behavior. Dashboard sends an explicit safer manual choice.
    publish_scope = str(data.get('publish_scope', 'all_enabled')).strip().lower()

    if content_mode not in {'organic', 'affiliate'}:
        return jsonify({'success': False, 'error': 'Невідомий режим контенту'}), 400
    if publish_scope not in {'create_only', 'youtube_only', 'all_enabled'}:
        return jsonify({'success': False, 'error': 'Невідома ціль публікації'}), 400
    profile = db.get_channel_profile(profile_id)
    if not profile:
        return jsonify({'success': False, 'error': 'Профіль каналу не знайдено'}), 404
    if content_mode == 'affiliate':
        offer = db.get_affiliate_offer(affiliate_offer_id or '')
        if not offer or offer.get('profile_id') != profile_id:
            return jsonify({
                'success': False,
                'error': 'Виберіть партнерську пропозицію для цього каналу'
            }), 400

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
            'content_mode': content_mode,
            'profile_id': profile_id,
            'affiliate_offer_id': affiliate_offer_id,
            'publish_scope': publish_scope,
            'trigger_source': trigger_source,
            'videos': []
        }
        db.start_automation_run(
            job_id, trigger_source, profile_id, content_mode
        )

    Thread(
        target=_run_generation_job,
        args=(
            job_id, count, niche, content_mode, profile_id,
            affiliate_offer_id, publish_scope, trigger_source
        ),
        daemon=True
    ).start()

    db.log_audit(
        'generation_started',
        {
            'job_id': job_id,
            'trigger_source': trigger_source,
            'profile_id': profile_id,
            'content_mode': content_mode,
            'publish_scope': publish_scope,
        },
        _client_ip(),
        1 if not g.automation_bot else None,
    )

    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': 'queued'
    }), 202


@app.route('/api/channel-profiles', methods=['GET', 'POST'])
def channel_profiles():
    """List profiles or create a clean destination for another YouTube account."""
    if request.method == 'GET':
        profiles = db.list_channel_profiles()
        return jsonify({'success': True, 'profiles': profiles})

    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    if not 2 <= len(name) <= 80:
        return jsonify({
            'success': False,
            'error': 'Назва профілю повинна містити від 2 до 80 символів'
        }), 400
    profile = db.create_channel_profile(name)
    db.log_audit(
        'channel_profile_created', {'profile_id': profile.get('profile_id')},
        _client_ip(), 1
    )
    return jsonify({'success': True, 'profile': profile}), 201


@app.route('/api/channel-profiles/<profile_id>', methods=['PATCH'])
def update_channel_profile(profile_id):
    data = request.get_json(silent=True) or {}
    mode = data.get('default_content_mode')
    if mode is not None and mode not in {'organic', 'affiliate'}:
        return jsonify({'success': False, 'error': 'Невідомий режим контенту'}), 400
    privacy = data.get('privacy_status')
    if privacy is not None and privacy not in {'public', 'unlisted', 'private'}:
        return jsonify({'success': False, 'error': 'Невідомий YouTube privacy status'}), 400
    try:
        profile = db.update_channel_profile(profile_id, data)
        db.log_audit(
            'channel_profile_updated', {'profile_id': profile_id},
            _client_ip(), 1
        )
        return jsonify({'success': True, 'profile': profile})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 404


@app.route('/api/affiliate-offers', methods=['GET', 'POST'])
def affiliate_offers():
    """Manage approved public affiliate links without exposing any API secrets."""
    if request.method == 'GET':
        profile_id = request.args.get('profile_id')
        return jsonify({
            'success': True,
            'offers': db.list_affiliate_offers(profile_id=profile_id)
        })

    data = request.get_json(silent=True) or {}
    profile_id = str(data.get('profile_id', '')).strip()
    name = str(data.get('name', '')).strip()
    url = str(data.get('url', '')).strip()
    description = str(data.get('description', '')).strip()
    parsed_url = urlparse(url)
    if not db.get_channel_profile(profile_id):
        return jsonify({'success': False, 'error': 'Профіль каналу не знайдено'}), 404
    if not 2 <= len(name) <= 100:
        return jsonify({'success': False, 'error': 'Вкажіть назву сервісу'}), 400
    if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
        return jsonify({'success': False, 'error': 'Вкажіть повне https-посилання'}), 400
    if not 10 <= len(description) <= 800:
        return jsonify({
            'success': False,
            'error': 'Опишіть перевірені функції сервісу (10–800 символів)'
        }), 400
    keywords = data.get('keywords', [])
    if isinstance(keywords, str):
        keywords = [item.strip() for item in keywords.split(',') if item.strip()]
    offer = db.create_affiliate_offer(profile_id, {
        'name': name,
        'url': url,
        'description': description,
        'keywords': list(keywords)[:12],
        'cta': str(data.get('cta', '')).strip(),
        'disclosure': str(data.get('disclosure', '')).strip(),
    })
    db.log_audit(
        'affiliate_offer_created',
        {'profile_id': profile_id, 'offer_id': offer.get('offer_id')},
        _client_ip(), 1
    )
    return jsonify({'success': True, 'offer': offer}), 201


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


@app.route('/api/bot/status')
def bot_status():
    return jsonify({
        'success': True,
        'official_api_only': True,
        'api_token_configured': bool(os.getenv('AUTOMATION_API_TOKEN')),
        'max_daily_posts_per_profile': producer.policy_guard.max_automated_daily,
        'runs': db.list_automation_runs(20),
    })


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
