"""Loopback-only dashboard and protected application controls."""
from datetime import datetime
import hmac
import math
import secrets

from flask import Flask, abort, jsonify, render_template, request

from utils import TIME_FORMAT, VERSION, os_type

HOST = '127.0.0.1:5000'
BASE_URL = 'http://' + HOST


def create_app(store, controller):
    app = Flask(__name__)
    app.config.update(CONTROL_TOKEN=secrets.token_urlsafe(32), MAX_CONTENT_LENGTH=4096,
                      DEBUG=False, TESTING=False)

    @app.before_request
    def local_only():
        if request.host != HOST:
            abort(403)
        origin = request.headers.get('Origin')
        if origin and origin != BASE_URL:
            abort(403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(403)
        if request.path.startswith('/control/') or request.path == '/end_program':
            token = request.headers.get('X-KMCounter-Token', '')
            if origin != BASE_URL or not hmac.compare_digest(token, app.config['CONTROL_TOKEN']):
                abort(403)

    @app.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self'; font-src 'self' data:; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(413)
    def request_error(error):
        return jsonify(error='请求无效或未获授权。请从托盘重新打开统计页。'), error.code

    @app.get('/')
    def index():
        return render_template('index.html', os_type=os_type, version=VERSION,
                               control_token=app.config['CONTROL_TOKEN'])

    @app.get('/status')
    def status():
        return jsonify(controller.status())

    @app.post('/fetch_key_counts')
    def fetch_key_counts():
        payload = request.get_json(silent=True)
        try:
            if not isinstance(payload, dict):
                raise ValueError
            start = datetime.strptime(payload.get('start_time', ''), '%Y-%m-%dT%H:%M')
            end = datetime.strptime(payload.get('end_time', ''), '%Y-%m-%dT%H:%M')
            if start > end:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(error='请选择有效的起止时间，开始时间不能晚于结束时间。'), 400
        counts = {}
        for minute, values in store.snapshot().items():
            if start <= datetime.strptime(minute, TIME_FORMAT) <= end:
                for key, count in values.items():
                    counts[key] = counts.get(key, 0) + count
        rates = {}
        for mouse in (False, True):
            group = {key: value for key, value in counts.items()
                     if key.startswith('Button.') == mouse and '_position_' not in key}
            maximum = max(group.values(), default=0)
            rates.update({key: math.log1p(value) / math.log1p(maximum)
                          for key, value in group.items() if maximum})
        rates.update({key: 0 for key in counts if '_position_' in key})
        return jsonify(counts, rates)

    @app.get('/fetch_total_key_counts')
    def fetch_total_key_counts():
        return jsonify({minute: sum(n for key, n in counts.items() if '_position_' not in key)
                        for minute, counts in store.snapshot().items()})

    @app.post('/control/<action>')
    def control(action):
        try:
            if action in ('pause', 'resume'):
                controller.set_paused(action == 'pause')
            elif action == 'stop':
                controller.request_stop()
            else:
                abort(404)
        except OSError:
            return jsonify(error='保存统计失败，请检查数据目录权限或可用空间。'), 503
        return jsonify(ok=True, **controller.status())

    @app.post('/end_program')
    def end_program():
        controller.request_stop()
        return jsonify(ok=True)

    return app
