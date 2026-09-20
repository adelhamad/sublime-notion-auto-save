# NotionSave

Adds **Save to Notion** to Sublime Text's editor context menu, tab context menu, File menu, and Command Palette. Saves the full buffer locally, closes the selected tab without a save prompt, and uploads it to your Notion database in a worker thread.

Targets Sublime Text 2 (build 2221+) with Python 2.6-compatible runtime code; also accommodates Sublime Text 3 and 4. Manual editor and live Notion verification are pending. Requires a `curl` executable with modern HTTPS/certificate support; there are no Python dependencies.

## Install for manual testing

1. Download this private repository's ZIP while signed into GitHub, or clone it.
2. In Sublime Text, choose **Preferences → Browse Packages…**.
3. Copy the extracted repository into that folder as **NotionSave**. `notion_save_plugin.py` must be directly inside `Packages/NotionSave/`, alongside `notion_save/`.
4. Restart Sublime Text.
5. Open the Command Palette and run **Notion: Settings**.

Alternatively, run `python3 scripts/build_package.py` to produce `dist/NotionSave.sublime-package`. Put that archive in Sublime's **Installed Packages** directory, which is next to **Packages**, then restart. Install either the source folder or the archive, not both.

## Connect Notion

Create an internal connection at [Notion's integration settings](https://www.notion.so/profile/integrations). Enable **Read content**, **Insert content**, and **Update content**. Add the connection to the target database using its **••• → Connections** menu.

Run **Notion: Settings**, enter your token and database URL or ID, then save:

```json
{
    "api_key": "YOUR_NOTION_API_TOKEN",
    "database_id": "YOUR_DATABASE_URL_OR_ID",
    "data_source_id": "",
    "curl_path": "curl"
}
```

Settings are stored in `Packages/User/Notion Save.sublime-settings`, outside the plugin repository. Leave the bundled settings empty. Instead of `api_key`, you can set `NOTION_API_KEY` in the environment inherited by Sublime (GUI-launched apps may not inherit shell variables).

- `database_id`: accepts a database ID or full Notion database URL. A database with one data source is resolved automatically.
- `data_source_id`: optional, takes precedence over `database_id`. Set it explicitly if the database has multiple data sources. The title property is discovered automatically.
- `curl_path`: defaults to `curl`. On macOS, `/usr/bin/curl` is an explicit alternative. On Windows/Linux, install a current curl if necessary and supply its absolute path.

No credentials are needed by the website or Vercel. Never commit your token.

## Use

Right-click in the editor or on a tab, then choose **Save to Notion**. The tab closes after a durable local snapshot; there is no network wait or upload dialog. The status bar reports the result. This command saves the **entire buffer**, not just the selection.

A saved file uses its filename as the Notion page title. An untitled buffer uses its first nonempty line (or `Untitled`). Text is stored in paragraph blocks, preserving text and whitespace within the blocks. Markdown syntax stays plain text. Long lines become multiple blocks; the per-buffer limit is 5 MB. Each invocation creates a new page, rather than updating an earlier page.

The source file on disk is not changed or deleted. Unsaved edits are included in the snapshot sent to Notion. Closing a tab does not quit Sublime; uploads run while the app is open. There is a small local disk-write cost before closing, which avoids losing the note if the app or network fails.

## Recovery

The queue is stored as plain-text JSON in `Packages/User/Notion Save Queue`. Queue entries contain the text and destination, never the API token. Successful uploads are removed. Queue files use owner-only permissions on POSIX; on Windows they inherit your user directory permissions.

- **Notion: Retry Uploads** retries pending and failed jobs after fixing credentials or permissions. Pending jobs retain their original destination, so changing the configured database affects new saves only. For an incorrectly selected destination, recover the text, remove the old entry while Sublime is closed, and save again.
- **Notion: Recover Pending Upload** lists snapshots and errors, and opens a copy of the selected text. The original queue entry is retained and may still upload.
- **Notion: Open Queue Folder** opens the snapshots for inspection or backup. Quit Sublime before manually editing or deleting queue entries.

Connection failures before sending, read failures, and rate limits retry with backoff (up to one hour between attempts). `Retry-After` is respected across the queue. Authentication/validation failures wait for **Retry Uploads**.

If a non-idempotent write times out, returns an ambiguous server error, or is interrupted by quitting Sublime, it is marked **uncertain** and is not automatically retried. Notion may have accepted the request. Check the database, recover the local copy, and only send it again if needed. A partially uploaded large note may already have a page; its ID and confirmed block offset are recorded in the queue file. Exactly-once delivery cannot be guaranteed across a remote write and a local process crash.

Pending jobs resume when Sublime restarts. An upload is **not guaranteed to continue after quitting the app**.

## Website / Vercel

`site/index.html` is a single static page with embedded CSS and JavaScript, plus a local JetBrains Mono font. It follows the visual style of [Adel Dev Tools](https://adel-dev-tools.vercel.app/). The editor preview is an illustrative demo and sends no data.

Import this repository into Vercel, keep the Root Directory at the repository root, and select **Other** for the framework. `vercel.json` publishes only `site/`, with no install/build command or environment variables. The Python plugin, tests, and queue are not deployed. Download links point to GitHub and require access while this repository is private.

Preview locally:

```sh
python3 -m http.server 8765 --directory site
```

## Package Control — prepared, not submitted

The proposed package name is **NotionSave**. See [the submission plan](docs/PACKAGE_CONTROL.md) and [manual test checklist](docs/MANUAL_TESTING.md). No public submission, release tag, or visibility change should happen until manual testing is complete and the owner authorizes publication.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_package.py
```

The suite uses fake Notion responses and Sublime API stubs. It covers durable snapshots, failure recovery, Unicode and request limits, destination resolution, thread behavior, rate-limit handling, secret handling, and saving/closing the correct tab. It does not replace manual testing in actual Sublime Text versions or a live Notion workspace.

Keep `notion_save_plugin.py` and `notion_save/` compatible with Python 2.6. Development scripts and tests use Python 3.10+.

References: [Sublime Text 2 API](https://www.sublimetext.com/docs/2/api_reference.html), [Notion create page](https://developers.notion.com/reference/post-page), [Notion limits](https://developers.notion.com/reference/request-limits), [Package Control submission](https://packagecontrol.io/docs/submitting_a_package).
