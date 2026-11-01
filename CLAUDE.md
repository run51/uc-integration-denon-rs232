# Project context — Denon RS-232 integration for Unfolded Circle

Read this file at the start of a session. It holds the context and decisions that cannot
be derived from the code. **Talk to the maintainer in French** (code, comments and
repository documentation stay in English).

## Goal

Control a **Denon AVP-A1HD** from an Unfolded Circle **Remote 3**, **without Home Assistant**,
through the unit's RS-232 port and the **Dock 3** TCP serial bridge.

Chain: `Remote 3 → driver (WebSocket Integration-API) → TCP 5000 → Dock 3 → jack/DB9 cable → Denon`

Replaces an ESPHome setup on a LILYGO T-RSS3 (which works and serves as reference/fallback).
The goal is to remove both the ESP **and** the Home Assistant machine from the chain.

## Current state

- Driver complete, 60 tests green, installed and working on the maintainer's Remote 3.
- Validated against `tests/denon_simulator.py` (fake Denon over TCP): connection, state
  queries, 30 s polling, reconnection.
- **Validated on the real unit** (Nov. 2026, Dock 3, TCP 5000): power on/off, source,
  surround mode, volume, mute, widget feedback, Room EQ, Dynamic EQ, Dynamic Volume,
  Reference Level, Quick 1-3. Not testable by the maintainer: zones 2/3/4 (single zone).
- **The driver is published: it exposes EVERY function of the unit** (DSX, zones 2/3/4…),
  even those the maintainer does not use. Never remove anything from the driver for a
  personal setup; adapt the activities/pages instead. (DSX was removed in 0.1.6, restored
  in 0.1.7.)
- **Nothing is released before the maintainer validates it on the real unit.** Work on a
  branch and build test versions (`X.Y.Z-testN` tags → GitHub pre-releases, never
  "latest"); tag the real version only after approval.
- The maintainer has a **Remote 3: no colour buttons** (the red/green/yellow → Quick mapping
  only helps Remote Two users). Quick 1-3 go through UI pages.
- The Remote 3 media widget shows only the **title and artist** lines (album is hidden);
  text alignment cannot be controlled by the driver.

## Architecture

Two layers, deliberately independent.

**`intg-denon/denon_control/`** — pure library, no Unfolded Circle dependency, reusable
from Home Assistant or a CLI:
- `transport.py`: asyncio TCP, CR framing, 60 ms pacing, 4 s hold after `PWON`
- `protocol.py`: stateless parser, one line → one typed `DenonEvent`
- `device.py`: state model + high-level commands, listener notifications
- `const.py`: **all protocol tables** (sources, modes, PS parameters)

**`intg-denon/`** — UC layer, built on `ucapi-framework` (JackJPowell):
- entities: 1 media player, 1 remote (4 UI pages, 162 simple commands), 18 selects,
  10 switches, 13 sensors
- `const.py`: **declarative** entity definitions (`SELECTS`, `SWITCHES`, `SENSORS`)
- `device.py`: `PersistentConnectionDevice`, update debounce, label ↔ protocol code
  translation, media widget lines

Structure inspired by `johncarey70/uc-integration-lumagen` (MPL-2.0).

## Denon protocol pitfalls — each one has its test

Observed on a real AVP-A1HD RS-232 capture. Do not break them:

1. **Fragmented frames**: `CVFL` then ` 405\r` in two reads. Accumulate until CR.
2. **`MVMAX 98`** follows every `MV`. A naive `startswith("MV")` would give −80 dB.
3. **`MSQUICK1`** has the `MS` prefix but is not a surround mode.
4. **`SVDVD` / `SVSOURCE`** are the video assignment, not the source (`SI`).
5. **Irregular PS separators**: `PSROOM EQ:AUDYSSEY`, `PSCINEMA EQ.ON`, `PSDSX ONH`.
6. **`PSDYN VOL`** is the Dynamic EQ parameter (value `VOL`); `PSDYNSET` is another
   parameter (prefixes tested longest first). `PSDYE ON` (truncated line) → `DYN`.
   **The unit ignores `PSDYNSET` unless `PSDYN` is `VOL`**: `send_raw` sends `PSDYN VOL` first.
7. **Unanswered queries** (`PSNIGHT ?`, `PSTONE DEFEAT ?` are silent) → fully event-driven
   architecture, no command waits for a reply.
8. **After `MVUP`**, the unit reports the old then the new value → 80 ms debounce.
9. **Protocol note K**: 4 s of silence required after `PWON`.
10. **In standby, the unit only answers `PW?`.**

Level decoding: `MV30` = −50.0 dB / `MV305` = −49.5 / code 80 = 0 dB.
`CV` channels: code 50 = 0 dB, range 38..62.

## Hardware — checked against the dock firmware

- **The Dock 3 has a real RS-232 transceiver.** No MAX3232, no TTL converter (the firmware
  release notes explicitly declare them unsupported).
- **Use external port 2 → TCP 5000.** Port 1 (4999) sends boot messages the unit would
  interpret as commands.
- Cable pinout: Tip (dock TX) → DB9 pin 3, Ring (RX) → pin 2, Sleeve → pin 5.
- Cable used: StarTech `9M351M-RS232-CABLE`. Beware, most generic cables use the opposite
  convention (pin 2 → Tip) and would need a null-modem.
- Dock settings: port 2 forced to RS232, 9600 8N1, TCP server enabled. No hot-plug.
- These settings are made in the **dock's web interface** (http://dock-ip, dock password),
  not on the Remote: with firmware 0.10.5 the Remote does not offer the RS232 mode.
- **The TCP server is a separate checkbox**, "RS232 TCP server (ports 4999, 5000)", off by
  default. Without it, port 5000 stays closed even with the port in RS232 mode.
- If every command comes back unchanged (echo), the jack is not fully inserted.

## Open points

1. **The unit received the "3D upgrade"** (Nov. 2011): the reference protocol is
   **version 6.0.2** (PDF in `ref/`, not versioned). `PSDYN OFF|ON|VOL` (single parameter),
   `PSDSX`, `PSREFLEV`, `PSFH:`, `PSPHG` added; **Night removed**. Verified live.
   The former ESPHome YAML (`denonavp.yaml`) is in the same folder.
2. **Zones 2/3/4**: never triggered, modelled from the PDF (mute and power off validated live).
3. **Source list**: the 13 non-North-American sources are present. Users may trim
   `denon_control/const.py::SOURCES` — everything else (simple commands, selects, UI pages)
   is regenerated automatically.

## Packaging constraints (learnt the hard way)

The archive installed on the Remote must follow the `core-api` specification
(`doc/integration-driver/driver-installation.md`):

- `.tar.gz`, `driver.json` **at the root**, aarch64 binary named `driver` in `./bin`
- **Icon: exactly 90×90 px, PNG or JPG, 16 KB max.** A 256×256 icon makes the Remote reject
  the archive with "Invalid archive, missing data or unreadable metadata".
- `driver_id` ≥ 5 characters, lowercase, no `uc_` prefix
- `developer` must include `name`, `email`, `url`

Build: GitHub workflow `Build & Release` (tag `v*` or manual trigger with the version
number). A version can only be used once — increment for every build. Versions containing
`test` are published as pre-releases. PyInstaller does not cross-compile: an ARM64 runner
is required.

Installing an update on the Remote = delete + reinstall: run the setup again, expose the
entities, then **restart the Remote** (otherwise the selects lose their option list).

## Maintainer environment

- Windows, GitHub repo `run51/uc-integration-denon-rs232`
- Python 3.13 locally (the project targets 3.11+, the Remote build uses 3.11)
- **mDNS discovery between Windows and the Remote does not work** in the maintainer's
  network — do not suggest the "external driver on PC" mode, use the archive installed
  on the Remote.
- Testing with the simulator: `python tests\denon_simulator.py 5000`, then configure the
  integration with the PC's IP.

## Conventions

- Code, comments and repository documentation in English; conversation with the
  maintainer in French.
- The protocol tables are the source of truth: adding a source or a mode is done in
  `denon_control/const.py` only.
- Every fix to a protocol pitfall must come with a test in `tests/test_protocol.py`.
- `pytest` must stay green before any commit.
