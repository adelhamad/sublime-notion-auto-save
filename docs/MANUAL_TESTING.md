# Manual test checklist

Use a disposable Notion database. All items below are pending until checked by the tester. Automated tests are not evidence that these editor/API checks passed.

Record:

- OS/version:
- Sublime Text version/build:
- Installation method (source folder or archive):
- curl version:
- Date:

## Install and configure

- [ ] Install once (no duplicate source-folder and archive installs), restart, and check Sublime's console for errors.
- [ ] Confirm “Save to Notion” in the editor context menu, tab context menu, File menu, and Command Palette.
- [ ] Run “Notion: Settings”; confirm it opens the user settings, not the bundled defaults.
- [ ] Configure the connection token and database URL. Grant Read, Insert, and Update content access; connect it to the database.
- [ ] Confirm missing token/invalid ID leaves the tab open with its unsaved state intact.

## Save and close

- [ ] Send an untitled note; verify quick close, no save dialog, correct Notion title and full content.
- [ ] Send a saved file with unsaved edits; verify Notion receives edits, while the disk file is unchanged.
- [ ] Right-click an inactive tab; verify that tab is sent and closed, not the active one.
- [ ] Test a cloned/split view; remaining views must still prompt for unsaved changes normally.
- [ ] Test blank text, Arabic, emoji, tabs, blank lines, CRLF, and a line longer than 2,000 characters.
- [ ] Test a note over 25 blocks; verify complete ordered content and a single Notion page.
- [ ] Test a database with a renamed title column and one with multiple data sources.
- [ ] Verify successful queue entries disappear and the status bar reports success.

## Failure and recovery

- [ ] Disconnect the network; save a note. Verify the tab closes, a queue snapshot exists, and the text uploads after reconnection.
- [ ] Use a revoked token or remove database access; verify recovery opens an exact copy. Fix access and run Retry Uploads.
- [ ] Quit and restart with pending work; verify it resumes or is held as uncertain if a write was interrupted.
- [ ] Review an uncertain job; verify Retry Uploads does not resend it automatically. Check Notion before sending a recovered copy.
- [ ] Verify the queue does not contain the API token and the console/process arguments do not expose it.
- [ ] Repeat with the built `.sublime-package`, including the legacy Package Control route if advertising ST2 support there.

## Website

- [ ] Open `site/index.html` through a local server or Vercel; check desktop and phone layouts.
- [ ] Test demo save/reset, copy settings, section links, FAQs, and authenticated GitHub download.

Publication remains blocked on manual approval, even if every automated check passes.
