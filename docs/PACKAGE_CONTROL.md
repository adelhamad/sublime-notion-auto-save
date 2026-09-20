# Package Control submission plan

Status: preparation only. **Do not submit, tag a release, or make the repository public until Adel finishes manual testing and explicitly approves publication.**

## Prepared

- Package name: `NotionSave` (ASCII, CamelCase, no redundant “Sublime” prefix).
- Plugin files at repository root, with no committed credentials, bytecode, or auto-generated `package-metadata.json`.
- Python 2.6-compatible runtime syntax for Sublime Text 2; relative-import support for later editors.
- Default settings, editor/tab/File menus, Command Palette entries, install message, and documentation.
- A package builder that uses an explicit allowlist, excluding tests, website, development files, and credentials.
- A draft channel entry in `docs/package-control-entry.json` using semantic-version tags, not branch releases.
- A manual test checklist and automated CI.

The official [submission guide](https://packagecontrol.io/docs/submitting_a_package) requires either a public GitHub/Bitbucket repository or public HTTPS package hosting. **The current private repository cannot be submitted as-is.** It stays private until a separate publication decision.

A Package Control search for “Notion” returned no packages on 2026-09-21. Repeat the [search](https://packagecontrol.io/search/Notion) before submission to confirm there is no substantially overlapping package or name conflict.

## After manual testing and approval

1. Complete `docs/MANUAL_TESTING.md`, recording the actual OS, Sublime build, curl version, and tested capabilities. Adjust the draft `sublime_text`/`platforms` constraints to match verified compatibility. ST2 users need a compatible legacy Package Control installation; test that route explicitly before claiming it works.
2. Choose an explicit distribution license and add `LICENSE`. Licensing is deliberately left undecided while the repository is private.
3. Choose public hosting: make this repository public only with explicit approval, or maintain a separate public distribution repository whose root contains the plugin. Update the channel entry and documentation links if the location changes.
4. Run the automated suite and build the `.sublime-package`. Test the archive installation as well as the source-folder installation. No bundled executables or shared libraries means `.no-sublime-package` is unnecessary.
5. Add release notes in `messages/1.0.0.txt` and the corresponding `messages.json` entry. Tag the tested commit with a semantic version such as `1.0.0`, then push the tag. No release tag has been created during preparation.
6. Fork [package_control_channel](https://github.com/wbond/package_control_channel). Add the draft entry to the appropriate `repository/n.json` package list, following that repository's current instructions.
7. Install ChannelRepositoryTools and run **ChannelRepositoryTools: Test Default Channel**, plus the channel repository's required checks.
8. Open a pull request with the package purpose, compatibility, dependency on curl, and validation results. Wait for maintainer review; do not claim the package is available before acceptance.

## Suggested future PR description

> Add NotionSave, a Sublime Text plugin that saves the current buffer to a selected Notion database, closes its tab after a durable local snapshot, and uploads in a worker thread. Includes recovery commands and conservative handling of ambiguous remote writes. Requires a Notion connection token and an external curl executable with modern HTTPS support.
>
> Tested manually on: [fill in editor builds and platforms after testing]. Automated validation: Python unittest suite and package build. Repository and semantic-version release tag: [fill in approved public URLs].
