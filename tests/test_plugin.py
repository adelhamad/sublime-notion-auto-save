import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from notion_save.core import Queue


class FakeView:
    def __init__(self, identity, text, buffer=None):
        self.identity, self.text = identity, text
        self.buffer = buffer or identity
        self.scratch = False
    def id(self): return self.identity
    def buffer_id(self): return self.buffer
    def is_scratch(self): return self.scratch
    def set_scratch(self, value): self.scratch = value
    def is_loading(self): return False
    def settings(self): return {}
    def substr(self, region): return self.text
    def size(self): return len(self.text)
    def file_name(self): return None
    def name(self): return ''


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.first = FakeView(1, 'First unsaved note')
        self.second = FakeView(2, 'Second unsaved note')
        self.views = [self.first, self.second]
        self.active = self.first
        self.window = Mock()
        self.window.active_view.side_effect = lambda: self.active
        self.window.views.side_effect = lambda: list(self.views)
        self.window.views_in_group.side_effect = lambda group: list(self.views)
        self.window.focus_view.side_effect = lambda view: setattr(self, 'active', view)
        self.window.run_command.side_effect = self.close
        self.sublime = types.ModuleType('sublime')
        self.sublime.version = lambda: '4200'
        self.sublime.set_timeout = Mock()
        self.sublime.status_message = Mock()
        self.sublime.error_message = Mock()
        self.sublime.windows = lambda: [self.window]
        self.sublime.Region = lambda a, b: (a, b)
        self.sublime.packages_path = lambda: self.temp.name
        self.sublime.load_settings = lambda name: {'api_key': 'test-placeholder', 'database_id': '1' * 32}
        self.sublime_plugin = types.ModuleType('sublime_plugin')
        self.sublime_plugin.WindowCommand = type('WindowCommand', (), {'__init__': lambda command, window: setattr(command, 'window', window)})
        self.sublime_plugin.TextCommand = type('TextCommand', (), {})
        self.modules = patch.dict(sys.modules, {'sublime': self.sublime, 'sublime_plugin': self.sublime_plugin})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        sys.modules.pop('notion_save_plugin', None)
        self.plugin = importlib.import_module('notion_save_plugin')
        self.sublime.version = lambda: '2221'
        self.worker = Mock()
        self.worker.queue = Queue(os.path.join(self.temp.name, 'queue'))
        self.worker_patch = patch.object(self.plugin, 'get_worker', return_value=self.worker)
        self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)
        self.command = self.plugin.NotionSaveCommand(self.window)

    def close(self, command):
        self.assertEqual(command, 'close_file')
        self.assertTrue(self.active.scratch)
        self.assertEqual(self.worker.queue.jobs()[0]['text'], self.active.text)
        self.views.remove(self.active)

    def test_snapshot_exists_before_unsaved_tab_closes(self):
        self.command.run()
        self.assertNotIn(self.first, self.views)
        self.assertEqual(self.worker.queue.jobs()[0]['text'], 'First unsaved note')
        self.worker.wake.set.assert_called_once()
        self.sublime.error_message.assert_not_called()

    def test_right_clicked_tab_is_saved_instead_of_active_tab(self):
        self.command.run(group=0, index=1)
        self.assertIn(self.first, self.views)
        self.assertNotIn(self.second, self.views)
        self.assertEqual(self.worker.queue.jobs()[0]['text'], 'Second unsaved note')

    def test_disk_failure_leaves_tab_open_and_dirty_behavior_intact(self):
        with patch.object(self.worker.queue, 'add', side_effect=OSError('disk full')):
            self.command.run()
        self.assertIn(self.first, self.views)
        self.assertFalse(self.first.scratch)
        self.window.run_command.assert_not_called()
        self.sublime.error_message.assert_called_once()

    def test_missing_configuration_leaves_tab_open(self):
        self.sublime.load_settings = lambda name: {}
        with patch.dict(os.environ, {}, clear=True):
            self.command.run()
        self.window.run_command.assert_not_called()
        self.assertEqual(self.worker.queue.jobs(), [])

    def test_other_clone_remains_unsaved(self):
        self.second.buffer = self.first.buffer
        self.command.run()
        self.assertIn(self.second, self.views)
        self.assertFalse(self.second.scratch)

    def test_failed_close_restores_scratch_flag(self):
        self.window.run_command.side_effect = None
        self.command.run()
        self.assertIn(self.first, self.views)
        self.assertFalse(self.first.scratch)
        self.assertEqual(len(self.worker.queue.jobs()), 1)

    def test_context_menu_can_be_hidden_without_hiding_palette(self):
        self.sublime.load_settings = lambda name: {'show_context_menu': False}
        self.assertFalse(self.command.is_visible(context_menu=True))
        self.assertTrue(self.command.is_visible())

    def test_context_menu_hidden_for_widgets_and_no_view(self):
        self.first.settings = lambda: {'is_widget': True}
        self.assertFalse(self.command.is_visible(context_menu=True))
        self.active = None
        self.assertFalse(self.command.is_visible(context_menu=True))
        self.assertFalse(self.command.is_enabled())

    def test_tab_menu_accepts_context_flag(self):
        self.command.run(group=0, index=1, context_menu=True)
        self.assertNotIn(self.second, self.views)
        self.assertIn(self.first, self.views)

    def test_modern_settings_use_split_editor_and_preserve_user_file(self):
        self.sublime.version = lambda: '4200'
        os.mkdir(os.path.join(self.temp.name, 'User'))
        path = os.path.join(self.temp.name, 'User', self.plugin.SETTINGS)
        with open(path, 'w') as handle:
            handle.write('{"api_key": "existing-placeholder"}')
        self.window.run_command.side_effect = None
        self.plugin.NotionSaveSettingsCommand(self.window).run()
        command, args = self.window.run_command.call_args.args
        self.assertEqual(command, 'edit_settings')
        self.assertEqual(args['user_file'], path)
        with open(path) as handle:
            self.assertIn('existing-placeholder', handle.read())

    def test_legacy_settings_open_in_two_groups(self):
        os.mkdir(os.path.join(self.temp.name, 'User'))
        settings_window = Mock()
        self.sublime.run_command = Mock()
        self.sublime.active_window = lambda: settings_window
        self.plugin.NotionSaveSettingsCommand(self.window).run()
        self.sublime.run_command.assert_called_once_with('new_window')
        self.assertEqual(settings_window.focus_group.call_args_list[0].args, (0,))
        self.assertEqual(settings_window.focus_group.call_args_list[1].args, (1,))
        self.assertEqual(settings_window.run_command.call_args_list[0].args[0], 'set_layout')
        settings_window.open_file.assert_called_once_with(
            os.path.join(self.temp.name, 'User', self.plugin.SETTINGS))


if __name__ == '__main__':
    unittest.main()
