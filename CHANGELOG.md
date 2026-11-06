# Changelog

## 0.1.0 (unreleased)

- Return to the hive now defaults to walking, like Natro (all 17 walk back routes converted; the
  converter handles Natro's loops, hive slot switches and bee count branches). Reset stays a per field option.
- Hive profile defaults added (colour, bee count 50, average bee level, Cub Buddy, backpack percent).

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
