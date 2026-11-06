# Changelog

## 0.1.0 (unreleased)

First packaged version, rebuilt the Natro way.

- Loop: reset to the hive, convert, replay a recorded walk to the field, gather in a
  pattern until the backpack pixel reads full, repeat. Death takes the same path.
- Natro's default walks for 17 fields plus cannon variants, 12 gather patterns, sprinkler
  settings, a Fields tab and a one button Calibrate tab.
- Remote control page for a phone (status, log, start, pause, stop, settings).
- Permissions checked with native macOS calls; Start refuses with a plain reason.
- HiveMac.app bundle with its own icon and launcher, data in
  ~/Library/Application Support/HiveMac; install and release scripts; CI builds the bundle.
- 53 tests, lint and compile clean. Gathering costs about 0.1% of one core.
