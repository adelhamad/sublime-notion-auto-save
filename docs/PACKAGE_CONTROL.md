# Package Control submission

Adel authorized publication, selected the MIT license, and made the existing repository public on 2026-09-21. This document tracks submission of **NotionSave 1.0.0**; acceptance into the default channel is a separate maintainer decision.

## Release

- Public repository: https://github.com/adelhamad/sublime-notion-auto-save
- Release: https://github.com/adelhamad/sublime-notion-auto-save/releases/tag/1.0.0
- License: MIT, copyright 2026 Adel Hamad.
- Package name: `NotionSave`; release selector: semantic-version tags.
- Target: Sublime Text build 2221+, all platforms with a modern curl executable.
- The root contains a single package. `.gitattributes` excludes the website, tests, scripts, workflow files, and design documents from GitHub package archives.
- No default key bindings. Editor/tab context entries are conditional and configurable with `show_context_menu`; the requested right-click workflow is enabled by default.
- Settings open side by side, using `edit_settings` on ST3 build 3124+ and an explicit two-group settings window on older builds.

## Validation

- Automated unittest suite: 36 tests, including persistence, retries, recovery, Unicode, transport, tab targeting, menu visibility, and settings behavior.
- Cross-platform CI covers Python 3.10 and 3.14 on macOS, Windows, and Linux. This validates Python behavior; it does not substitute for running every legacy Sublime editor build.
- Package archive built and verified with an explicit file allowlist.
- Package Control's current package reviewer passes with no failures. Its settings-name advisory is intentional: `Notion Save.sublime-settings` is retained to preserve existing user credentials and configuration.
- The current channel schema validator passes locally. The channel's own PR checks will validate the submitted revision again.
- No Notion integration package or NotionSave name conflict was found in the default channel at submission preparation time.

The owner's request to publish follows their manual trial. Unchecked items in [MANUAL_TESTING.md](MANUAL_TESTING.md) are not claimed as verified.

## Submission

The proposed entry is in [package-control-entry.json](package-control-entry.json) and belongs in `repository/n.json` in [sublimehq/package_control_channel](https://github.com/sublimehq/package_control_channel).

Submission PR: pending creation.

The maintainer must participate in review and address feedback. Package Control availability starts only after acceptance and channel indexing. Until then, users can install the archive from the GitHub release.

## Future releases

1. Address issues and rerun the tests and package reviewer.
2. Add release notes to `messages/` and update `messages.json`.
3. Build and inspect the archive; commit the final changes.
4. Create and push a new semantic-version tag, and attach the archive to its GitHub release.
5. Leave existing release tags unchanged so installed versions remain reproducible.

References: [submission guide](https://packagecontrol.io/docs/submitting_a_package), [current channel guidance](https://docs.sublimetext.io/guide/package-control/submitting.html), [channel pull request template](https://github.com/sublimehq/package_control_channel/blob/master/.github/PULL_REQUEST_TEMPLATE.md).
