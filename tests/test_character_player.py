import base64
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from pixel_asset_pipeline.character_player import write_player


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class CharacterPlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'player.html'
        self.metadata = {'artboard': 'Character', 'state_machine': 'Character Actions',
                         'number_input': 'action', 'size': [96, 64],
                         'states': [{'name': 'idle', 'value': 4, 'loop': True, 'duration_ms': 500},
                                    {'name': 'custom <& "動作', 'value': 9, 'loop': False, 'duration_ms': 750}]}

    def test_offline_payload_preserves_order_values_and_official_runtime(self):
        write_player(self.output, b'RIVEtest', self.metadata, 'Scout', 'ja')
        document = self.output.read_text()
        payload = json.loads(re.search(r'id="player-data">(.*?)</script>', document, re.S)[1])
        self.assertEqual(payload['config']['states'][0]['label'], '待機')
        self.assertEqual([state['value'] for state in payload['config']['states']], [4, 9])
        self.assertEqual(payload['config']['states'][1]['label'], 'custom <& "動作')
        self.assertEqual(base64.b64decode(payload['riv']), b'RIVEtest')
        vendor = Path(__file__).parents[1] / 'src/pixel_asset_pipeline/player/vendor'
        self.assertEqual(base64.b64decode(payload['runtime']), (vendor / 'rive.js').read_bytes())
        self.assertEqual(base64.b64decode(payload['wasm']), (vendor / 'rive.wasm').read_bytes())
        self.assertIn('Copyright (c) 2020-2021 Rive', document)
        for _, attrs in Document(document).tags:
            self.assertNotIn('src', attrs)
            self.assertFalse(attrs.get('href', '').startswith(('https:', 'http:')))
        self.assertIn("connect-src data: blob:", document)

    def test_title_and_action_cannot_inject_html_or_script(self):
        title = '</title><script>alert(1)</script>@@DATA@@'
        self.metadata['states'][1]['name'] = '</script><img src=x onerror=alert(2)>'
        write_player(self.output, b'RIVEtest', self.metadata, title, 'ko')
        document = self.output.read_text()
        tags = Document(document).tags
        self.assertFalse(any(tag == 'img' or 'onerror' in attrs for tag, attrs in tags))
        self.assertEqual(sum(tag == 'script' for tag, _ in tags), 2)
        payload = json.loads(re.search(r'id="player-data">(.*?)</script>', document, re.S)[1])
        self.assertEqual(payload['config']['title'], title)
        self.assertIn('&lt;/title&gt;', document)
        self.assertEqual(payload['config']['states'][0]['label'], '대기')

    def test_tampered_runtime_is_rejected_before_writing(self):
        root = Path(self.temp.name) / 'template'
        vendor = root / 'vendor'
        vendor.mkdir(parents=True)
        (vendor / 'integrity.json').write_text(json.dumps({'sha256': {'rive.js': '0' * 64}}))
        (vendor / 'rive.js').write_bytes(b'tampered')
        with patch('pixel_asset_pipeline.character_player._PLAYER', root), self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            write_player(self.output, b'RIVEtest', self.metadata, 'Scout', 'ko')
        self.assertFalse(self.output.exists())

    def test_invalid_metadata_is_rejected_before_writing(self):
        cases = [{'size': [0, 96]}, {'states': []}, {'number_input': ''},
                 {'states': [dict(self.metadata['states'][0], value=float('nan'))]},
                 {'states': [dict(self.metadata['states'][0], value=10 ** 400)]},
                 {'states': [dict(self.metadata['states'][0], duration_ms=-1)]},
                 {'states': [self.metadata['states'][0], self.metadata['states'][0]]}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                write_player(self.output, b'RIVEtest', self.metadata | change, 'Scout', 'ko')
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            write_player(self.output, b'not-rive', self.metadata, 'Scout', 'ko')
        with self.assertRaises(ValueError):
            write_player(self.output, b'RIVEtest', self.metadata, 'Scout', 'en')


if __name__ == '__main__':
    unittest.main()
