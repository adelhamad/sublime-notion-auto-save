"""Save a buffer locally, close its tab, then send it to Notion off the UI thread."""
from __future__ import unicode_literals

import os
import sublime
import sublime_plugin

try:
    from .notion_save.core import Queue, Worker, notion_id, CurlClient
except (ImportError, ValueError):
    from notion_save.core import Queue, Worker, notion_id, CurlClient

SETTINGS = "Notion Save.sublime-settings"
_previous_worker = globals().get("_worker") or globals().get("_previous_worker")
if _previous_worker:
    _previous_worker.stop()
_worker = None
_generation = object()
_unloaded = False


def notify(message):
    # set_timeout is the only thread-safe Sublime Text 2 API.
    sublime.set_timeout(lambda: sublime.status_message(message), 0)


def configuration():
    settings = sublime.load_settings(SETTINGS)
    token = (settings.get("api_key", "") or os.environ.get("NOTION_API_KEY", "")).strip()
    return {"token": token, "curl_path": settings.get("curl_path", "curl") or "curl"}


def destination():
    settings = sublime.load_settings(SETTINGS)
    source = settings.get("data_source_id", "") or ""
    database = settings.get("database_id", "") or ""
    if source.strip():
        return {"data_source_id": notion_id(source)}
    if database.strip():
        return {"database_id": notion_id(database)}
    raise ValueError("Set database_id or data_source_id in Notion Save settings first.")


def get_worker():
    global _worker
    if _previous_worker and _previous_worker.is_alive():
        raise ValueError("Notion Save is finishing a request after reloading. Try again shortly.")
    if _worker is None:
        queue = Queue(os.path.join(sublime.packages_path(), "User", "Notion Save Queue"))
        _worker = Worker(queue, notify)
        _worker.configure(configuration())
        _worker.start()
    return _worker


def tick(generation):
    if _unloaded or generation is not _generation:
        return
    try:
        get_worker().configure(configuration())
    except Exception:
        pass  # Save command reports configuration/storage errors without closing.
    sublime.set_timeout(lambda: tick(generation), 5000)


def plugin_loaded():
    tick(_generation)


def plugin_unloaded():
    global _unloaded
    _unloaded = True
    if _worker:
        _worker.stop()


if int(sublime.version()) < 3000:
    # ST2 initializes its API before importing plugins and has no plugin_loaded hook.
    # ST3+ invokes plugin_loaded itself after its asynchronous API initialization.
    plugin_loaded()


class NotionSaveCommand(sublime_plugin.WindowCommand):
    def target(self, group=-1, index=-1):
        if group >= 0 and index >= 0:
            views = self.window.views_in_group(group)
            return views[index] if index < len(views) else None
        return self.window.active_view()

    def is_enabled(self, group=-1, index=-1, context_menu=False):
        view = self.target(group, index)
        return view is not None and not view.is_loading() and not view.settings().get("is_widget", False)

    def is_visible(self, group=-1, index=-1, context_menu=False):
        if not context_menu:
            return True
        return (sublime.load_settings(SETTINGS).get("show_context_menu", True)
                and self.is_enabled(group, index))

    def run(self, group=-1, index=-1, context_menu=False):
        view = self.target(group, index)
        if not view or view.is_loading():
            return
        try:
            config = configuration()
            CurlClient(config["token"], config["curl_path"])  # Local validation only.
            target = destination()
            worker = get_worker()
            worker.configure(config)
            text = view.substr(sublime.Region(0, view.size()))
            title = os.path.basename(view.file_name()) if view.file_name() else view.name()
            if not title:
                title = next((line.strip()[:120] for line in text.splitlines() if line.strip()), "Untitled")
            worker.queue.add(text, title, target)
        except Exception as error:
            sublime.error_message("Notion Save: %s\n\nYour tab is still open. Use Notion: Settings to configure the plugin." % error)
            return

        # The durable snapshot exists before suppressing Sublime's save prompt.
        # Keep the dirty/scratch behavior of any cloned views intact.
        related = [(other, other.is_scratch()) for window in sublime.windows()
                   for other in window.views() if other.buffer_id() == view.buffer_id()]
        self.window.focus_view(view)
        view.set_scratch(True)
        try:
            self.window.run_command("close_file")
        finally:
            remaining = [other.id() for window in sublime.windows() for other in window.views()]
            for other, scratch in related:
                if other.id() in remaining:
                    other.set_scratch(scratch)
            worker.wake.set()
        sublime.status_message("Queued for Notion: " + title)


class NotionSaveSettingsCommand(sublime_plugin.WindowCommand):
    def run(self):
        path = os.path.join(sublime.packages_path(), "User", SETTINGS)
        if not os.path.exists(path):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write('{\n    "api_key": "",\n    "database_id": "",\n    "data_source_id": "",\n    "curl_path": "curl"\n}\n')
        package = __package__ or os.path.basename(os.path.dirname(__file__))
        if int(sublime.version()) >= 3124:
            self.window.run_command("edit_settings", {
                "base_file": "${packages}/" + package + "/" + SETTINGS,
                "user_file": path
            })
        else:
            # edit_settings was added in ST3 build 3124; preserve ST2 support.
            sublime.run_command("new_window")
            window = sublime.active_window()
            window.run_command("set_layout", {
                "cols": [0.0, 0.5, 1.0], "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            })
            window.focus_group(0)
            window.run_command("open_file", {
                "file": "${packages}/" + package + "/" + SETTINGS
            })
            window.focus_group(1)
            window.open_file(path)


class NotionRetryUploadsCommand(sublime_plugin.WindowCommand):
    def run(self):
        get_worker().configure(configuration(), retry=True)
        sublime.status_message("Retrying pending/failed Notion uploads. Uncertain uploads require recovery and review.")


class NotionRecoverUploadCommand(sublime_plugin.WindowCommand):
    def run(self):
        queue = get_worker().queue
        jobs = [job for job in queue.jobs() if job["state"] != "done"]
        if not jobs:
            sublime.status_message("No pending Notion uploads.")
            return
        items = [[job["title"], job["state"] + ": " + job.get("error", "Waiting to upload")] for job in jobs]

        def selected(index):
            if index < 0:
                return
            job = jobs[index]
            if job["state"] == "corrupt":
                self.window.open_file(os.path.join(queue.folder, job["id"] + ".json"))
                return
            view = self.window.new_file()
            view.set_name(job["title"] + " (recovered)")
            view.run_command("notion_restore_text", {"text": job["text"]})
            sublime.status_message("Recovered a copy; original queue entry retained. Check Notion before sending again.")

        self.window.show_quick_panel(items, selected)


class NotionRestoreTextCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.insert(edit, 0, text)


class NotionOpenQueueCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command("open_dir", {"dir": get_worker().queue.folder})
