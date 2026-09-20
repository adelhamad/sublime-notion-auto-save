"""Python 2.6-compatible persistence and Notion transport; no Sublime API calls."""
from __future__ import unicode_literals

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid

API_VERSION = "2025-09-03"
MAX_BYTES = 5 * 1024 * 1024


class UploadError(Exception):
    def __init__(self, message, retry=False, uncertain=False, delay=30, throttled=False):
        Exception.__init__(self, message)
        self.retry = retry
        self.uncertain = uncertain
        self.delay = delay
        self.throttled = throttled


def notion_id(value):
    value = value.strip().split("?")[0].rstrip("/")
    match = re.search(r"([a-fA-F0-9]{32}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})$", value)
    if not match:
        raise ValueError("Enter a valid Notion database/data source ID or database URL.")
    return str(uuid.UUID(match.group(1)))


def chunks(text, size=1000):
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Python 2.6 may use narrow Unicode; never split a surrogate pair.
        if end < len(text) and 0xD800 <= ord(text[end - 1]) <= 0xDBFF:
            end -= 1
        yield text[start:end]
        start = end


def blocks(text):
    result = []
    for line in text.splitlines(True):
        for part in chunks(line):
            result.append({"object": "block", "type": "paragraph", "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": part}}]}})
    return result


def atomic_write(path, data):
    folder = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(data, ensure_ascii=True).encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            import ctypes
            move = ctypes.windll.kernel32.MoveFileExW
            move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
            if not move(temporary, path, 0x1 | 0x8):
                raise ctypes.WinError()
        else:
            os.rename(temporary, path)
            directory = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


class Queue(object):
    def __init__(self, folder):
        self.folder = folder
        if not os.path.isdir(folder):
            os.makedirs(folder, 0o700)

    def save(self, job):
        atomic_write(os.path.join(self.folder, job["id"] + ".json"), job)

    def add(self, text, title, destination):
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("This buffer exceeds the 5 MB upload limit; split it first.")
        job = {"id": uuid.uuid4().hex, "text": text, "title": title,
               "destination": destination, "state": "pending", "offset": 0,
               "created": time.time(), "attempts": 0, "next_attempt": 0}
        self.save(job)
        return job

    def jobs(self):
        jobs = []
        for name in sorted(os.listdir(self.folder)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.folder, name), "rb") as handle:
                    job = json.loads(handle.read().decode("utf-8"))
                if job.get("id") + ".json" != name or "text" not in job:
                    raise ValueError("Invalid queue entry")
                jobs.append(job)
            except (ValueError, TypeError, KeyError, AttributeError, IOError):
                # Preserve damaged files; surface their location for recovery.
                jobs.append({"id": name[:-5], "title": name, "state": "corrupt",
                             "error": "Unreadable queue file: " + os.path.join(self.folder, name)})
        return jobs


def config_quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


class CurlClient(object):
    def __init__(self, token, executable="curl"):
        if not token or re.search(r"[\x00-\x20\x7f]", token):
            raise ValueError("Set a valid Notion API token in Notion Save settings.")
        self.token = token
        self.executable = executable

    def request(self, method, path, body=None):
        # Both token and text travel through stdin, never shell/argv or temp files.
        config = ["url = " + config_quote("https://api.notion.com/v1/" + path),
                  "header = " + config_quote("Authorization: Bearer " + self.token),
                  "header = " + config_quote("Notion-Version: " + API_VERSION),
                  'header = "Content-Type: application/json"']
        if body is not None:
            config.append("data-binary = " + config_quote(json.dumps(body, ensure_ascii=True)))
        args = [self.executable, "-q", "--config", "-", "--silent", "--show-error",
                "--proto", "=https", "--connect-timeout", "10", "--max-time", "45",
                "--request", method, "--include", "--write-out", "\n%{http_code}"]
        startup = None
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startup.wShowWindow = 0  # SW_HIDE, including Python 2.6.
        try:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, startupinfo=startup)
        except OSError:
            raise UploadError("Cannot start curl. Set curl_path to a working curl executable.")
        output, unused_stderr = process.communicate(("\n".join(config) + "\n").encode("utf-8"))
        if process.returncode:
            safe_to_retry = method == "GET" or process.returncode in (5, 6, 7, 35, 60)
            raise UploadError("Network/TLS failure (curl %s). Local copy retained." % process.returncode,
                              retry=safe_to_retry, uncertain=not safe_to_retry)
        try:
            raw, status = output.rsplit(b"\n", 1)
            status = int(status)
            headers = b""
            while raw.startswith(b"HTTP/"):
                header, raw = raw.split(b"\r\n\r\n", 1)
                headers += header + b"\r\n"
        except (ValueError, UnicodeError):
            raise UploadError("Unexpected Notion response. Local copy retained.",
                              retry=method == "GET", uncertain=method != "GET")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            if 200 <= status < 300:
                raise UploadError("Unexpected Notion response. Local copy retained.",
                                  retry=method == "GET", uncertain=method != "GET")
            payload = {}
        if 200 <= status < 300:
            return payload
        retry_after = re.findall(br"(?im)^retry-after:\s*(\d+)", headers)
        delay = max(1, int(retry_after[-1])) if retry_after else 30
        code = payload.get("code", "http_error") if isinstance(payload, dict) else "http_error"
        # Do not echo response messages, which can contain the submitted text.
        message = "Notion HTTP %s (%s). Local copy retained." % (status, code)
        retry = status in (429, 529) or (method == "GET" and status >= 500)
        uncertain = method != "GET" and status >= 500 and status != 529
        raise UploadError(message, retry=retry, uncertain=uncertain, delay=delay,
                          throttled=status in (429, 529))


def resolve_destination(client, destination):
    source_id = destination.get("data_source_id")
    if not source_id:
        database = client.request("GET", "databases/" + destination["database_id"])
        sources = database.get("data_sources", [])
        if len(sources) != 1:
            raise UploadError("Database has %s data sources; set data_source_id explicitly." % len(sources))
        source_id = notion_id(sources[0]["id"])
    source = client.request("GET", "data_sources/" + source_id)
    titles = [key for key, value in source.get("properties", {}).items() if value.get("type") == "title"]
    if len(titles) != 1:
        raise UploadError("Cannot identify the data source title property. Check connection access.")
    return source_id, titles[0]


def upload(queue, job, client, stopped=lambda: False, pause=lambda: None):
    if "source_id" not in job:
        job["source_id"], job["title_property"] = resolve_destination(client, job["destination"])
        queue.save(job)
    content = blocks(job["text"])
    while "page_id" not in job or job["offset"] < len(content):
        if stopped():
            return
        batch = content[job["offset"]:job["offset"] + 25]
        if "page_id" not in job:
            title = next(chunks(job["title"] or "Untitled"))
            method, path = "POST", "pages"
            body = {"parent": {"type": "data_source_id", "data_source_id": job["source_id"]},
                    "properties": {job["title_property"]: {"title": [{"type": "text", "text": {"content": title}}]}},
                    "children": batch}
        else:
            method, path = "PATCH", "blocks/" + job["page_id"] + "/children"
            body = {"children": batch}
        # Persist intent before any non-idempotent write. A crash here needs review.
        job["state"] = "sending"
        queue.save(job)
        response = client.request(method, path, body)
        if method == "POST":
            if not isinstance(response, dict) or not response.get("id"):
                raise UploadError("Notion returned no page ID; check Notion before retrying.", uncertain=True)
            job["page_id"] = notion_id(response["id"])
            job["url"] = response.get("url", "")
        job["offset"] += len(batch)
        job["state"] = "pending"
        queue.save(job)
        pause()
    job["state"] = "done"
    queue.save(job)
    os.remove(os.path.join(queue.folder, job["id"] + ".json"))


class Worker(threading.Thread):
    def __init__(self, queue, notify, client_factory=CurlClient):
        threading.Thread.__init__(self)
        self.daemon = True
        self.queue = queue
        self.notify = notify
        self.client_factory = client_factory
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.config = {}
        self.retry_requested = False

    def configure(self, config, retry=False):
        with self.lock:
            changed = config != self.config
            self.config = dict(config)
            self.retry_requested = self.retry_requested or retry
        if changed or retry:
            self.wake.set()

    def stop(self):
        self.stop_event.set()
        self.wake.set()

    def cycle(self):
        jobs = self.queue.jobs()
        if any(job.get("throttle_until", 0) > time.time() for job in jobs):
            return
        with self.lock:
            config = dict(self.config)
            retry = self.retry_requested
            self.retry_requested = False
        for job in jobs:
            if self.stop_event.is_set():
                return
            state = job["state"]
            if state == "done":
                os.remove(os.path.join(self.queue.folder, job["id"] + ".json"))
                continue
            if state == "sending":
                job["state"] = "uncertain"
                job["error"] = "Upload interrupted; check Notion before saving a recovered copy."
                self.queue.save(job)
                self.notify(job["error"])
                continue
            if state in ("uncertain", "corrupt"):
                continue
            if retry:
                job["state"], job["next_attempt"] = "pending", 0
                job["attempts"] = 0
            if job["state"] != "pending" or job["next_attempt"] > time.time() or not config.get("token"):
                continue
            try:
                client = self.client_factory(config["token"], config.get("curl_path", "curl"))
                upload(self.queue, job, client, self.stop_event.is_set,
                       lambda: self.stop_event.wait(0.4))
                if job["state"] == "done":
                    self.notify("Saved to Notion: " + job["title"])
            except UploadError as error:
                job["attempts"] += 1
                job["state"] = "uncertain" if error.uncertain else ("pending" if error.retry else "failed")
                job["error"] = str(error)
                job["next_attempt"] = time.time() + max(error.delay, min(3600, 5 * 2 ** min(job["attempts"], 10)))
                if error.throttled:
                    job["throttle_until"] = job["next_attempt"]
                self.queue.save(job)
                self.notify(job["error"] + " Use Notion: Recover Pending Upload.")
                if error.throttled:
                    return
            except Exception:
                job["state"] = "uncertain" if job["state"] == "sending" else "failed"
                job["error"] = "Upload stopped unexpectedly. Local copy retained; review pending uploads."
                self.queue.save(job)
                self.notify(job["error"])

    def run(self):
        while not self.stop_event.is_set():
            self.wake.clear()
            try:
                self.cycle()
            except Exception:
                self.notify("Notion queue could not be updated. Check disk space and queue folder permissions.")
            self.wake.wait(5)
