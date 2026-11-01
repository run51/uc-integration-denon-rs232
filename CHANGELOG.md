# Changelog

## v0.1.8

- Media widget shows the unit's state on the two lines displayed by the Remote 3:
  - line 1: volume · Muted · source (volume first, so it is always at the same place);
  - line 2: surround mode · Room EQ ("EQ Off" when off) · Dynamic EQ, with the
    Dynamic Volume level when enabled (e.g. "Dyn EQ+Vol Evening").
- Project documentation translated to English.
- Build workflow: versions containing `test` (e.g. `0.1.8-test1`) are published as
  pre-releases and never marked as latest.

## v0.1.7

- Audyssey DSX restored (select, sensor, commands, Audyssey page buttons): the driver
  exposes every function of the unit, even those a given installation does not use.

## v0.1.6

- Dynamic Volume: choosing Day / Evening / Midnight automatically enables
  "Dynamic EQ + Volume" (`PSDYN VOL`) before sending the level. The unit ignores
  `PSDYNSET` while Dynamic Volume is off (verified on the real unit).
- Audyssey DSX removed (restored in v0.1.7).

## v0.1.5

- AVP-A1HD "3D upgrade" protocol (Denon 6.0.2), verified on the real unit:
  - Dynamic EQ / Dynamic Volume become a single `PSDYN` select:
    Off / Dynamic EQ / Dynamic EQ + Volume (the former `PSDYNEQ` / `PSDYNVOL` commands
    never existed). The Day / Evening / Midnight level (`PSDYNSET`) is unchanged.
  - Added Audyssey DSX (Off / Height / Wide, stage width and height), Dynamic EQ
    reference level (0 / 5 / 10 / 15 dB) and Dolby PLIIz Height (on/off, gain).
  - Night mode removed, as the upgrade removed it from the unit.
- Remote "Audyssey" UI page rebuilt accordingly.

## v0.1.4

- The media player widget shows the unit's state: source (title line), surround mode
  (artist line) and volume in dB, with "Muted" when muted (album line).
  Lines are cleared in standby.

## v0.1.3

- Stable device identifier (`denon`), independent of the bridge IP address.
  Changing the IP (simulator → Dock 3) no longer renames the entities nor breaks the
  activities and pages using them. Entities of an existing configuration are renamed
  one last time when upgrading to this version.

## v0.1.0

- First version: Denon AVP-A1HD over RS-232 through a TCP bridge (Dock 3, IP2SL…).
- Standalone `denon_control` layer: TCP transport with CR framing, typed parser, state model.
- Media player, Remote (4 UI pages, 151 simple commands, raw pass-through), 15 selects,
  11 switches, 13 sensors.
- Automatic reconnection, 30 s safety polling, refresh after power on.
- Denon simulator and 47 tests (parser replaying a real capture, end-to-end).
- Default TCP port 5000 (Dock 3 external port 2; port 1 sends boot messages).
- Wiring documentation: the Dock 3 has an RS-232 transceiver, a plain crossed jack/DB9
  cable is enough.
