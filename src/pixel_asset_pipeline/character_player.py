"""Write an offline, self-contained preview using the official Rive runtime."""
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import re


_PLAYER = Path(__file__).with_name('player')
_LABELS = {
    'ko': {'idle': '대기', 'walk': '걷기', 'run': '달리기', 'attack': '공격', 'jump': '점프',
           'hurt': '피격', 'wave': '손 흔들기', 'cheer': '환호'},
    'ja': {'idle': '待機', 'walk': '歩く', 'run': '走る', 'attack': '攻撃', 'jump': 'ジャンプ',
           'hurt': 'ダメージ', 'wave': '手を振る', 'cheer': '喜ぶ'},
}
_TEXT = {
    'ko': {'intro': '동작을 선택하고, 다시 보기로 처음부터 재생하세요.', 'actions': '동작 선택',
           'loading': '캐릭터를 불러오는 중…', 'pause': '일시 정지', 'resume': '계속 재생',
           'replay': '동작 다시 보기 ↻', 'playing': '재생 중', 'paused': '일시 정지',
           'complete': '재생 완료', 'error': '캐릭터 또는 동작 입력을 불러오지 못했습니다.',
           'download': 'Rive 파일 다운로드 ↓'},
    'ja': {'intro': '動作を選び、もう一度ボタンで最初から再生できます。', 'actions': '動作を選択',
           'loading': 'キャラクターを読み込み中…', 'pause': '一時停止', 'resume': '再生を続ける',
           'replay': 'もう一度 ↻', 'playing': '再生中', 'paused': '一時停止',
           'complete': '再生完了', 'error': 'キャラクターまたは動作の入力を読み込めませんでした。',
           'download': 'Rive ファイルをダウンロード ↓'},
}


def write_player(output: Path, riv_bytes: bytes, metadata: dict, title: str, language: str = 'ko') -> None:
    """Write to an exact HTML path; metadata is the ``rive.json`` export contract."""
    if language not in _TEXT:
        raise ValueError('player language must be ko or ja')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('player title must be nonempty text')
    if not isinstance(riv_bytes, bytes) or not riv_bytes.startswith(b'RIVE'):
        raise ValueError('player requires Rive bytes')
    if not isinstance(metadata, dict):
        raise ValueError('player requires Rive metadata')
    for key in ('artboard', 'state_machine', 'number_input'):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f'player metadata requires {key}')
    size = metadata.get('size')
    if not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or not 1 <= n <= 512 for n in size):
        raise ValueError('player size must contain two integers in 1..512')
    states = metadata.get('states')
    if not isinstance(states, list) or not 1 <= len(states) <= 32:
        raise ValueError('player requires 1..32 states')
    values, names, actions = set(), set(), []
    for state in states:
        if not isinstance(state, dict):
            raise ValueError('invalid player state')
        name, value, duration = state.get('name'), state.get('value'), state.get('duration_ms')
        if (not isinstance(name, str) or not name.strip() or len(name) > 80 or name in names
                or type(value) not in (int, float) or not -9_007_199_254_740_991 <= value <= 9_007_199_254_740_991
                or not math.isfinite(value) or value in values
                or type(state.get('loop')) is not bool
                or type(duration) not in (int, float) or not 0 < duration <= 120_000):
            raise ValueError('invalid player state')
        names.add(name)
        values.add(value)
        actions.append({key: state[key] for key in ('name', 'value', 'loop', 'duration_ms')})
        actions[-1]['label'] = _LABELS[language].get(name, name)
    vendor = _PLAYER / 'vendor'
    integrity = json.loads((vendor / 'integrity.json').read_text())
    files = {}
    for name, digest in integrity['sha256'].items():
        data = (vendor / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Rive runtime integrity mismatch: {name}')
        files[name] = data
    config = {key: metadata[key] for key in ('artboard', 'state_machine', 'number_input', 'size')}
    config.update(states=actions, title=title, text=_TEXT[language])
    payload = {'config': config, 'riv': base64.b64encode(riv_bytes).decode(),
               'runtime': base64.b64encode(files['rive.js']).decode(),
               'wasm': base64.b64encode(files['rive.wasm']).decode(),
               'fallback': base64.b64encode(files['rive_fallback.wasm']).decode()}
    slots = {'LANG': language, 'TITLE': html.escape(title), 'INTRO': _TEXT[language]['intro'],
             'LOADING': _TEXT[language]['loading'], 'ACTIONS': _TEXT[language]['actions'],
             'PAUSE': _TEXT[language]['pause'], 'REPLAY': _TEXT[language]['replay'],
             'DOWNLOAD': _TEXT[language]['download'], 'LICENSE': html.escape(files['LICENSE'].decode()),
             'CSS': (_PLAYER / 'style.css').read_text(), 'JS': (_PLAYER / 'player.js').read_text(),
             'DATA': json.dumps(payload, ensure_ascii=True).replace('<', '\\u003c')}
    template = (_PLAYER / 'index.html').read_text()
    output.write_text(re.sub(r'@@([A-Z]+)@@', lambda match: slots[match[1]], template), encoding='utf-8')
