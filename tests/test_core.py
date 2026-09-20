import json
import os
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from notion_save import core

DB = '11111111-1111-1111-1111-111111111111'
DS = '22222222-2222-2222-2222-222222222222'
PAGE = '33333333-3333-3333-3333-333333333333'


class FakeClient:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.failure:
            failure = self.failure(method, path, body)
            if failure:
                raise failure
        if path.startswith('databases/'):
            return {'data_sources': [{'id': DS}]}
        if path.startswith('data_sources/'):
            return {'properties': {'Note title': {'type': 'title'}}}
        return {'id': PAGE, 'url': 'https://www.notion.so/' + PAGE}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = core.Queue(os.path.join(self.temp.name, 'queue'))

    def job(self, text='A note\nWith another line'):
        return self.queue.add(text, 'Test note', {'database_id': DB})

    def worker(self, client):
        worker = core.Worker(self.queue, lambda message: None, lambda *args: client)
        worker.configure({'token': 'test-only-placeholder'})
        return worker

    def test_database_url_ignores_view_id(self):
        self.assertEqual(core.notion_id('https://notion.so/Notes-' + DB.replace('-', '') + '?v=' + DS), DB)
        with self.assertRaises(ValueError):
            core.notion_id('invalid-id')

    def test_unicode_roundtrip_and_private_snapshot(self):
        text = 'مرحبا 🌍\n\n日本語\ttext\r\n'
        self.job(text)
        job = core.Queue(self.queue.folder).jobs()[0]
        self.assertEqual(job['text'], text)
        self.assertNotIn('token', job)
        path = os.path.join(self.queue.folder, job['id'] + '.json')
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_failed_snapshot_does_not_replace_original(self):
        job = self.job()
        original = self.queue.jobs()[0]
        job['text'] = 'changed'
        with patch.object(core.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.queue.save(job)
        self.assertEqual(self.queue.jobs()[0], original)
        self.assertFalse(any(name.startswith('.pending') for name in os.listdir(self.queue.folder)))

    def test_large_buffer_rejected_without_queue_entry(self):
        with self.assertRaises(ValueError):
            self.job('x' * (core.MAX_BYTES + 1))
        self.assertEqual(self.queue.jobs(), [])

    def test_corrupt_files_preserved(self):
        path = os.path.join(self.queue.folder, 'bad.json')
        with open(path, 'w') as handle:
            handle.write('[')
        self.assertEqual(self.queue.jobs()[0]['state'], 'corrupt')
        self.assertTrue(os.path.exists(path))

    def test_complete_upload_and_title_discovery(self):
        client = FakeClient()
        core.upload(self.queue, self.job(), client)
        self.assertEqual(self.queue.jobs(), [])
        body = client.calls[2][2]
        self.assertEqual(body['parent']['data_source_id'], DS)
        self.assertIn('Note title', body['properties'])

    def test_direct_data_source_and_empty_note(self):
        client = FakeClient()
        job = self.queue.add('', 'Empty', {'data_source_id': DS})
        core.upload(self.queue, job, client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1][2]['children'], [])
        self.assertEqual(self.queue.jobs(), [])

    def test_multiple_data_sources_need_explicit_selection(self):
        class Multiple(FakeClient):
            def request(self, *args):
                return {'data_sources': [{'id': DB}, {'id': DS}]}
        with self.assertRaises(core.UploadError):
            core.resolve_destination(Multiple(), {'database_id': DB})

    def test_chunk_boundaries_and_request_sizes(self):
        text = ('🌍' * 3500 + '\r\n\t' + 'a' * 2000 + '\n') * 15
        client = FakeClient()
        core.upload(self.queue, self.job(text), client)
        writes = [body for method, path, body in client.calls if method != 'GET']
        self.assertGreater(len(writes), 1)
        recovered = ''
        for body in writes:
            self.assertLess(len(json.dumps(body).encode()), 500000)
            self.assertLessEqual(len(body['children']), 25)
            for block in body['children']:
                part = block['paragraph']['rich_text'][0]['text']['content']
                self.assertLessEqual(len(part.encode('utf-16-le')) // 2, 2000)
                recovered += part
        self.assertEqual(recovered, text)

    def test_narrow_unicode_surrogates_not_split(self):
        text = 'a' * 999 + '\ud83c\udf0d' + 'z'
        parts = list(core.chunks(text))
        self.assertEqual(parts[0], 'a' * 999)
        self.assertEqual(parts[1], '\ud83c\udf0dz')

    def test_offline_retry_and_restart(self):
        self.job()
        client = FakeClient(lambda *args: core.UploadError('offline', retry=True))
        self.worker(client).cycle()
        saved = self.queue.jobs()[0]
        self.assertEqual(saved['state'], 'pending')
        self.assertGreater(saved['next_attempt'], time.time())
        good = FakeClient()
        worker = self.worker(good)
        worker.configure({'token': 'test-only-placeholder'}, retry=True)
        worker.cycle()
        self.assertEqual(self.queue.jobs(), [])

    def test_failed_auth_retained_and_manual_retry(self):
        self.job()
        worker = self.worker(FakeClient(lambda *args: core.UploadError('unauthorized')))
        worker.cycle()
        self.assertEqual(self.queue.jobs()[0]['state'], 'failed')
        worker.client_factory = lambda *args: FakeClient()
        worker.configure({'token': 'fixed-placeholder'}, retry=True)
        worker.cycle()
        self.assertEqual(self.queue.jobs(), [])

    def test_interrupted_write_is_not_automatically_duplicated(self):
        job = self.job()
        job['state'] = 'sending'
        self.queue.save(job)
        client = FakeClient()
        worker = self.worker(client)
        worker.cycle()
        self.assertEqual(self.queue.jobs()[0]['state'], 'uncertain')
        worker.configure({'token': 'test-only-placeholder'}, retry=True)
        worker.cycle()
        self.assertEqual(client.calls, [])

    def test_ambiguous_timeout_keeps_snapshot(self):
        self.job()
        def failure(method, *args):
            if method == 'POST':
                return core.UploadError('timeout', uncertain=True)
        self.worker(FakeClient(failure)).cycle()
        self.assertEqual(self.queue.jobs()[0]['state'], 'uncertain')

    def test_partial_upload_resumes_without_recreating_page(self):
        self.job('line\n' * 60)
        def failure(method, *args):
            if method == 'PATCH':
                return core.UploadError('rate limited', retry=True)
        self.worker(FakeClient(failure)).cycle()
        saved = self.queue.jobs()[0]
        self.assertEqual(saved['page_id'], PAGE)
        self.assertEqual(saved['offset'], 25)
        client = FakeClient()
        worker = self.worker(client)
        worker.configure({'token': 'test-only-placeholder'}, retry=True)
        worker.cycle()
        self.assertTrue(all(method == 'PATCH' for method, path, body in client.calls))
        self.assertEqual(sum(len(body['children']) for method, path, body in client.calls), 35)

    def test_throttling_pauses_all_jobs_even_after_restart(self):
        self.job('first')
        self.job('second')
        client = FakeClient(lambda *args: core.UploadError('rate', retry=True, throttled=True, delay=120))
        worker = self.worker(client)
        worker.cycle()
        self.assertEqual(len(client.calls), 1)
        restarted = self.worker(client)
        restarted.configure({'token': 'test-only-placeholder'}, retry=True)
        restarted.cycle()
        self.assertEqual(len(client.calls), 1)

    def test_upload_uses_worker_thread(self):
        self.job()
        entered, release = threading.Event(), threading.Event()
        thread_ids = []
        class Slow(FakeClient):
            def request(inner, *args):
                thread_ids.append(threading.get_ident())
                entered.set()
                release.wait(3)
                return super().request(*args)
        worker = self.worker(Slow())
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertNotEqual(thread_ids[0], threading.get_ident())
            self.queue.add('another note', 'Next', {'database_id': DB})
        finally:
            worker.stop()
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())


class TransportTests(unittest.TestCase):
    def request(self, output, method='POST', returncode=0):
        with patch.object(core.subprocess, 'Popen') as popen:
            process = popen.return_value
            process.returncode = returncode
            process.communicate.return_value = output, b''
            result = core.CurlClient('test-secret').request(method, 'pages', {'children': []})
            return result, popen

    def test_token_and_content_not_in_process_arguments(self):
        result, popen = self.request(b'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n{"id":"ok"}\n200')
        self.assertEqual(result, {'id': 'ok'})
        args = popen.call_args.args[0]
        self.assertNotIn('test-secret', ' '.join(args))
        self.assertNotIn('children', ' '.join(args))
        self.assertEqual(args[1], '-q')
        stdin = popen.return_value.communicate.call_args.args[0]
        self.assertIn(b'Authorization: Bearer test-secret', stdin)

    def test_rate_limit_header_with_proxy_and_interim_headers(self):
        raw = b'HTTP/1.1 200 Connection established\r\n\r\nHTTP/1.1 100 Continue\r\n\r\nHTTP/2 429\r\nRetry-After: 91\r\n\r\n{"code":"rate_limited"}\n429'
        with self.assertRaises(core.UploadError) as caught:
            self.request(raw)
        self.assertTrue(caught.exception.retry)
        self.assertTrue(caught.exception.throttled)
        self.assertEqual(caught.exception.delay, 91)

    def test_html_overload_response_is_retryable(self):
        with self.assertRaises(core.UploadError) as caught:
            self.request(b'HTTP/2 529\r\nRetry-After: 72\r\n\r\n<html>Busy</html>\n529')
        self.assertTrue(caught.exception.retry)
        self.assertEqual(caught.exception.delay, 72)

    def test_timeout_post_is_uncertain_get_is_retryable(self):
        for method in ['POST', 'GET']:
            with self.assertRaises(core.UploadError) as caught:
                self.request(b'', method, 28)
            self.assertEqual(caught.exception.uncertain, method == 'POST')
            self.assertEqual(caught.exception.retry, method == 'GET')

    def test_connect_failure_safe_to_retry(self):
        with self.assertRaises(core.UploadError) as caught:
            self.request(b'', returncode=7)
        self.assertTrue(caught.exception.retry)
        self.assertFalse(caught.exception.uncertain)

    def test_server_error_post_not_blindly_retried(self):
        with self.assertRaises(core.UploadError) as caught:
            self.request(b'HTTP/2 500\r\n\r\n{"code":"internal_server_error"}\n500')
        self.assertFalse(caught.exception.retry)
        self.assertTrue(caught.exception.uncertain)

    def test_token_config_injection_rejected(self):
        with self.assertRaises(ValueError):
            core.CurlClient('token\nurl = evil')

    def test_config_escaping_roundtrips_json(self):
        payload = json.dumps({'text': 'quotes " and \\ paths\n🌍'})
        quoted = core.config_quote(payload)
        self.assertEqual(json.loads(quoted), payload)


if __name__ == '__main__':
    unittest.main()
