"""Build a clean Sublime package without site assets, tests, or user credentials."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'notion_save_plugin.py',
    'notion_save/__init__.py',
    'notion_save/core.py',
    'Notion Save.sublime-settings',
    'Notion Save.sublime-commands',
    'Context.sublime-menu',
    'Tab Context.sublime-menu',
    'Main.sublime-menu',
    'messages.json',
    'README.md',
]


def build():
    # Validate the shipped defaults; reject accidental credential configuration.
    settings_text = (ROOT / 'Notion Save.sublime-settings').read_text()
    settings = json.loads('\n'.join(line for line in settings_text.splitlines()
                                    if not line.lstrip().startswith('//')))
    for key in ('api_key', 'database_id', 'data_source_id'):
        if settings.get(key):
            raise SystemExit('Refusing to package nonempty default ' + key)
    files = list(FILES)
    messages = json.loads((ROOT / 'messages.json').read_text())
    for value in messages.values():
        path = Path(value)
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'messages':
            raise SystemExit('Invalid message path: ' + value)
        files.append(value)
    if (ROOT / 'LICENSE').is_file():
        files.append('LICENSE')
    output = ROOT / 'dist' / 'NotionSave.sublime-package'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(files)):
            archive.write(ROOT / name, name)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise SystemExit('Archive verification failed')
    print(output)
    return output


if __name__ == '__main__':
    build()
