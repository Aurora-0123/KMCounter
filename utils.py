"""Local aggregate storage. Never store event sequences or arbitrary text."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import tempfile
import threading

VERSION = '2.0.0'
TIME_FORMAT = '%Y-%m-%d %H:%M'
os_type = platform.system()
_SHIFTED = dict(zip('~!@#$%^&*()_+{}|:"<>?', '`1234567890-=[]\\;\',./'))
_SPECIAL = set(('alt alt_l alt_r alt_gr backspace caps_lock cmd cmd_l cmd_r ctrl '
                'ctrl_l ctrl_r delete down end enter esc home insert left menu '
                'num_lock page_down page_up pause print_screen right scroll_lock '
                'shift shift_l shift_r space tab up media_volume_mute media_volume_down '
                'media_volume_up media_play_pause media_next media_previous unknown').split())
_SPECIAL.update(f'f{n}' for n in range(1, 25))
_BUTTON = re.compile(r'^Button\.(?:left|right|middle|x1|x2)(?:_position_-?\d+_-?\d+)?$')


def normalize_key(key: str) -> str:
    if _BUTTON.fullmatch(key):
        if '_position_' in key:
            button, position = key.split('_position_')
            x, y = map(int, position.split('_'))
            return f'{button}_position_{max(0, min(99, x))}_{max(0, min(99, y))}'
        return key
    if key == 'Key.shift_l':
        return 'Key.shift'
    if key.startswith('Key.') and key[4:] in _SPECIAL:
        return key
    if len(key) == 1:
        if 1 <= ord(key) <= 26:
            return chr(ord(key) + 64)
        if key.isascii() and key.isalpha():
            return key.upper()
        if key in _SHIFTED:
            return _SHIFTED[key]
        if key in "0123456789`-=[]\\;',./":
            return key
    return 'Key.unknown'


def normalize_history(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError('Invalid history')
    result = {}
    for minute, counts in value.items():
        if not isinstance(minute, str) or datetime.strptime(minute, TIME_FORMAT).strftime(TIME_FORMAT) != minute:
            raise ValueError('Invalid minute')
        if not isinstance(counts, dict):
            raise ValueError('Invalid counts')
        result[minute] = {}
        for name, count in counts.items():
            if not isinstance(name, str) or type(count) is not int or count < 0:
                raise ValueError('Invalid count')
            if count:
                key = normalize_key(name)
                result[minute][key] = result[minute].get(key, 0) + count
    return result


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
            json.dump(value, f, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class StatsStore:
    def __init__(self, directory: Path, clock=datetime.now):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        self._days = {}
        self._dirty = set()
        self._errors = {}
        self.paused = False

    @property
    def errors(self):
        with self.lock:
            return list(self._errors.values())

    def _load(self, day):
        if day not in self._days:
            path = self.directory / f'{day}.json'
            try:
                value = normalize_history(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else {}
                if any(not minute.startswith(day + ' ') for minute in value):
                    raise ValueError('History date mismatch')
                self._days[day] = value
                self._errors.pop(day, None)
            except (OSError, ValueError, TypeError):
                self._errors[day] = f'无法读取 {day}.json；已保留原文件，请检查或从备份恢复。'
                raise ValueError('Unable to read history') from None
        return self._days[day]

    def _count(self, keys):
        with self.lock:
            if self.paused:
                return
            now = self.clock()
            day, minute = now.strftime('%Y-%m-%d'), now.strftime(TIME_FORMAT)
            counts = self._load(day).setdefault(minute, {})
            for key in keys:
                counts[key] = counts.get(key, 0) + 1
            self._dirty.add(day)

    def count_key(self, name):
        self._count([normalize_key(name)])

    def count_click(self, button, x, y, bounds):
        if button not in {'Button.left', 'Button.right', 'Button.middle', 'Button.x1', 'Button.x2'}:
            return
        left, top, width, height = bounds
        px = max(0, min(99, int((x - left) / max(1, width) * 100)))
        py = max(0, min(99, int((y - top) / max(1, height) * 100)))
        self._count([button, f'{button}_position_{px}_{py}'])

    def set_paused(self, paused):
        with self.lock:
            self.paused = bool(paused)
            self.flush()

    def flush(self):
        with self.lock:
            for day in sorted(self._dirty):
                try:
                    atomic_json(self.directory / f'{day}.json', self._days[day])
                except OSError:
                    self._errors['write:' + day] = f'保存 {day}.json 失败；内存统计仍保留，将继续重试。'
                    raise
                else:
                    self._errors.pop('write:' + day, None)
                    self._dirty.remove(day)

    def snapshot(self):
        with self.lock:
            days = set(self._days)
            days.update(p.stem for p in self.directory.glob('????-??-??.json'))
            result = {}
            for day in sorted(days):
                try:
                    result.update({minute: dict(counts) for minute, counts in self._load(day).items()})
                except ValueError:
                    continue
            return dict(sorted(result.items()))

    def import_legacy(self, source, sample_hashes=()):
        source = Path(source)
        if not source.exists() or source.resolve() == self.directory.resolve():
            return
        with self.lock:
            for path in sorted(source.glob('????-??-??.json')):
                try:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() in sample_hashes:
                        continue
                    incoming = normalize_history(json.loads(raw))
                    if any(not minute.startswith(path.stem + ' ') for minute in incoming):
                        raise ValueError('Date mismatch')
                    current = self._load(path.stem)
                    # Max merge is idempotent even after a crash between imports.
                    for minute, counts in incoming.items():
                        target = current.setdefault(minute, {})
                        for key, count in counts.items():
                            target[key] = max(target.get(key, 0), count)
                    self._dirty.add(path.stem)
                    self.flush()
                    self._errors.pop('import:' + path.name, None)
                except (OSError, ValueError, TypeError):
                    self._errors['import:' + path.name] = f'未能导入 {path.name}；原始记录已保留。'
