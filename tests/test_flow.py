import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend.detection import analyze

class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"NETRA_ENGINE": "rules"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_three_routes(self):
        with patch.dict(os.environ, {"NETRA_ENGINE":"rules"}, clear=True):
            self.assertEqual(analyze('Bank accounts and ATM cards available for rent. DM @demo_seller')['verdict'], 'flagged')
            self.assertEqual(analyze('Same stuff as last time, two packs ready')['verdict'], 'unclear')
            self.assertEqual(analyze('Hi team, meeting tomorrow. Thanks!')['verdict'], 'no_flags')

    def test_news_is_not_flagged_as_a_trade(self):
        with patch.dict(os.environ, {"NETRA_ENGINE":"rules"}, clear=True):
            self.assertEqual(analyze('News report: police arrested a seller offering cocaine for sale')['verdict'], 'unclear')

    def test_model_outage_goes_to_review(self):
        with patch.dict(os.environ, {'OLLAMA_MODEL':'test','NETRA_ENGINE':'llama'}), patch('urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertEqual(analyze('Hi, meeting tomorrow')['verdict'], 'unclear')

    def test_model_response_and_evidence_validation(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'done':True,'message':{'content':json.dumps({'language':'English','understood':True,'verdict':'flagged', 'categories':['Weapons','invented'], 'reason':'Potential sale', 'evidence':['pistol', 'invented evidence']})}}).encode()
        with patch.dict(os.environ, {'OLLAMA_MODEL':'test','NETRA_ENGINE':'llama'}), patch('urllib.request.urlopen', return_value=response):
            result = analyze('pistol for sale')
        self.assertEqual(result['engine'], 'Llama · test')
        self.assertEqual(result['categories'], ['Weapons'])
        self.assertEqual(result['evidence'], ['pistol'])

    def model_result(self, text, output):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'done':True,'message':{'content':json.dumps(output)}}).encode()
        with patch.dict(os.environ, {'NETRA_ENGINE':'llama'}), patch('urllib.request.urlopen', return_value=response) as request:
            result = analyze(text)
            payload = json.loads(request.call_args.args[0].data)
            self.assertEqual(payload['model'], 'llama3.2:3b')
            self.assertEqual(payload['messages'][0]['role'], 'system')
            self.assertEqual(json.loads(payload['messages'][1]['content'])['message'], text)
        return result

    def test_hinglish_model_response(self):
        result = self.model_result('Bhai ganja chahiye, delivery ho jayegi?', {'language':'Hinglish','understood':True,'verdict':'flagged','categories':['Drugs'],'reason':'Potential request for drugs.','evidence':['ganja chahiye']})
        self.assertEqual(result['verdict'], 'flagged')
        self.assertEqual(result['language'], 'Hinglish')
        self.assertEqual(result['review_reason'], 'suspected_trade')

    def test_regional_scripts_bypass_model_even_with_wrong_hint(self):
        for text in ['நாளை காலை சந்திக்கலாம்', 'কাল দেখা হবে', 'రేపు కలుద్దాం', 'Hello, ਕੱਲ੍ਹ ਮਿਲਦੇ ਹਾਂ']:
            with patch('urllib.request.urlopen') as request:
                result = analyze(text, 'english')
            request.assert_not_called()
            self.assertEqual(result['verdict'], 'unclear')
            self.assertEqual(result['review_reason'], 'unsupported_language')

    def test_explicit_local_language_bypasses_model(self):
        with patch('urllib.request.urlopen') as request:
            result = analyze('naale kaanam', 'other')
        request.assert_not_called()
        self.assertEqual(result['review_reason'], 'unsupported_language')

    def test_model_cannot_clear_unsupported_or_uncertain_language(self):
        for language, understood in [('Other',True),('Unknown',False),('Hinglish',False)]:
            result = self.model_result('naale kaanam', {'language':language,'understood':understood,'verdict':'no_flags','categories':[],'reason':'Meaning uncertain','evidence':[]})
            self.assertEqual(result['verdict'], 'unclear')

    def test_malformed_language_response_is_not_cleared(self):
        result = self.model_result('hello', {'language':'Hinglish','verdict':'no_flags','categories':[],'reason':'Routine','evidence':[]})
        self.assertEqual(result['review_reason'], 'model_unavailable')

    def test_invalid_language_hint(self):
        with self.assertRaises(ValueError):
            analyze('hello', 'unsupported')

class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{cls.port}'
        env = dict(os.environ, NETRA_ENGINE='rules', NETRA_DB=str(Path(cls.temp.name) / 'test.db'), PORT=str(cls.port), AUTHORITY_PASSWORD='test-password')
        env.pop('OLLAMA_MODEL', None)
        cls.process = subprocess.Popen([sys.executable, '-m', 'backend.server'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for _ in range(60):
            try:
                urllib.request.urlopen(cls.base + '/api/health', timeout=1).close()
                return
            except OSError:
                time.sleep(.05)
        cls.process.terminate()
        raise RuntimeError('Test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.temp.cleanup()

    def request(self, path, data=None, client=None):
        req = urllib.request.Request(self.base + path, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
        with (client or self.client).open(req) as response:
            return json.load(response)

    def test_end_to_end_review_and_persistence(self):
        item = self.request('/api/analyze', {'text':'Bank accounts available for rent. DM @demo_seller', 'source':'Synthetic demo'})
        self.assertEqual(item['status'], 'pending')
        self.request('/api/login', {'password':'test-password'})
        rows = self.request('/api/messages')['messages']
        self.assertTrue(any(x['id'] == item['id'] for x in rows))
        self.request('/api/review', {'id':item['id'], 'status':'investigating', 'note':'Request more context.'})
        saved = next(x for x in self.request('/api/messages')['messages'] if x['id'] == item['id'])
        self.assertEqual(saved['status'], 'investigating')
        self.assertEqual(saved['note'], 'Request more context.')
        import sqlite3
        with sqlite3.connect(Path(self.temp.name) / 'test.db') as db:
            self.assertEqual(db.execute('SELECT note FROM messages WHERE id=?', (item['id'],)).fetchone()[0], 'Request more context.')
        db.close()
        self.request('/api/logout', {})

    def test_protected_endpoints(self):
        anonymous = urllib.request.build_opener()
        for path, data in [('/api/messages',None),('/api/review',{'id':'test','status':'dismissed'})]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path, data, anonymous)
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

    def test_invalid_input_and_unknown_context(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/analyze', {'text':' '})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        item = self.request('/api/analyze', {'text':'xqz pack blue code 72'})
        self.assertEqual(item['analysis']['verdict'], 'unclear')
        self.assertEqual(item['status'], 'pending')

    def test_routine_not_queued(self):
        item = self.request('/api/analyze', {'text':'Hi, meeting at lunch tomorrow. Thanks!'})
        self.assertEqual(item['status'], 'screened')

    def test_local_language_is_stored_for_authority_review(self):
        item = self.request('/api/analyze', {'text':'naale kaanam','language_hint':'other'})
        self.assertEqual(item['status'], 'pending')
        self.assertEqual(item['analysis']['review_reason'], 'unsupported_language')
        self.assertEqual(item['analysis']['language_hint'], 'other')

    def test_api_rejects_invalid_language_hint(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/analyze', {'text':'hello','language_hint':['other']})
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_cross_origin_rejected(self):
        req = urllib.request.Request(self.base + '/api/analyze', data=b'{"text":"hello"}', headers={'Content-Type':'application/json', 'Origin':'https://other.example'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_interface_and_assets_are_served(self):
        for path, content_type in [('/', 'text/html'), ('/app.js', 'text/javascript'), ('/styles.css', 'text/css')]:
            with urllib.request.urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(content_type, response.headers['Content-Type'])
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
                self.assertTrue(response.read())

if __name__ == '__main__':
    unittest.main()
