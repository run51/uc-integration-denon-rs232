# Denon AV receivers & processors (RS-232) — Unfolded Circle integration

Controls Denon AV receivers and processors from an Unfolded Circle Remote Two/3,
**without Home Assistant**, through the unit's RS-232 port and a serial-to-IP bridge —
typically the TCP server of the **Unfolded Circle Dock 3** (ports 4999/5000), but also
Global Caché IP2SL/iTach, USR-TCP232, ser2net…

Built and tested with the RS-232 commands of the **Denon AVP-A1HD** (with the 2011
"3D upgrade"). It works with other Denon units of the same generation that use the same
ASCII protocol (`PWON` / `MV80` / `SIDVD`…).

## Compatibility

Checked against Denon's official RS-232 protocol documents:

| Function | AVP-A1HD (3D upgrade) | AVP-A1HD (original) | AVR-4308CI | AVR-3808CI |
|---|---|---|---|---|
| Power, volume, mute | ✅ | ✅ | ✅ | ✅ |
| Sources, surround modes, Quick Select 1-3 | ✅ | ✅ | ✅ | ✅ |
| Room EQ, Cinema EQ, Restorer, DRC | ✅ | ✅ | ✅ | ✅ |
| Zones 2/3/4, channel levels | ✅ | ✅ | ✅ | ✅ |
| Dynamic EQ / Dynamic Volume | ✅ | ⚠️ different command | ❌ | ❌ |
| Reference Level, Audyssey DSX, PLIIz | ✅ | ❌ | ❌ | ❌ |

- Tested on real hardware: AVP-A1HD with the 3D upgrade, through a Dock 3.
- Very likely compatible (protocol documents not found): AVC-A1HD (same platform as the
  AVP-A1HD) and AVR-5308CI (same generation as the AVR-4308CI).
- On the AVR-3808CI / 4308CI the source is called `DVR` (not `DVR-1` / `DVR-2`), and the
  Home THX Cinema and Dolby H/P modes do not exist.

Reports from owners of other models are welcome.

```
Remote 3 ──WS──▶ this driver ──TCP 5000──▶ Dock 3 ──3.5 mm jack / DB9 cable──▶ Denon
```

Real-time feedback: the unit pushes every change on its own, and the driver updates the
entities without aggressive polling (one safety refresh every 30 s).

Tested on a real AVP-A1HD (with the 2011 "3D upgrade") through a Dock 3: power on/off,
source, surround mode, volume, mute, Room EQ, Dynamic EQ / Dynamic Volume, Reference Level
and Quick Select 1-3. Zones 2/3/4 are implemented from the protocol specification but have
not been tested on real hardware yet — feedback welcome.

## Entities

| Type | Content |
|---|---|
| **Media player** | Power, volume (0-100 ↔ −80…+18 dB), mute, source list, surround mode list, D-pad, menu |
| **Remote** | Physical buttons mapped, 4 UI pages (Sources, Surround, Audyssey, Quick/Zones), 162 simple commands, raw pass-through |
| **18 Selects** | Source, Surround, Input mode, Digital mode, Quick Select, Room EQ, Dynamic EQ (Off / EQ / EQ + Volume), Dynamic Volume (Day / Evening / Midnight), Reference Level, Audyssey DSX, PLIIz Height Gain, Audio Restorer, PL mode, DRC, D.COMP, zone 2/3/4 sources |
| **10 Switches** | Mute, Main zone, PLIIz Height, Cinema EQ, Tone Defeat, zones 2/3/4, zone 2/3 mute |
| **13 Sensors** | Volume (dB), source, surround, input mode, quick select, Room EQ, Dyn EQ, Dyn Vol, Audyssey DSX, Restorer, zone 2 |

### Media widget

The Remote 3 media widget shows two text lines, used to display the unit's state:

```
-50.0 dB · DVD                              ← volume · Muted · source
Stereo · Audyssey · Dyn EQ+Vol Evening      ← surround mode · Room EQ · Dynamic EQ / Volume
```

The lines are cleared when the unit is in standby.

### Notes

- **Dynamic Volume**: the unit ignores the Day / Evening / Midnight level (`PSDYNSET`) unless
  Dynamic Volume is enabled. Choosing a level therefore switches Dynamic EQ to
  "Dynamic EQ + Volume" first.
- **Quick Select**: the colour buttons (red/green/yellow → Quick 1/2/3) only exist on the
  Remote Two. On a Remote 3, use the `QUICK1`…`QUICK3` commands on an activity page, or the
  driver's "Quick / Zones" UI page.

## Hardware

### The Dock 3 has a real RS-232 transceiver

**No level shifter is needed.** The dock outputs standard RS-232 levels directly on the
jack: a plain 3.5 mm jack ↔ DB9 cable is enough.

Conversely, TTL UART adapters are not supported, as their signal levels differ — do not put
a MAX3232 module or a TTL converter between the two.

### Use external port 2 (TCP 5000)

On current docks, RS232 mode is limited to external port 2. Port 1 may send system messages
at boot that the unit would interpret as commands — the ESP32 boot console would end up in
the Denon.

| Dock external port | TCP port | Usable for RS232 |
|---|---|---|
| 1 | 4999 | not recommended |
| **2** | **5000** | **yes** |

### Cable pinout

On the dock side, in RS232 mode: **Tip = TX**, **Ring = RX**, **Sleeve = GND**. Unfolded
Circle insists on following this pinout strictly for home-made cables, otherwise detection
problems or damage may occur.

The Denon is a DCE with a female DB9: pin 2 = TxD (it transmits), pin 3 = RxD (it
receives), pin 5 = GND. The cable is therefore crossed:

| 3.5 mm jack (dock) | Male DB9 (to the Denon) |
|---|---|
| **Tip** — dock TX | **pin 3** — Denon RxD |
| **Ring** — dock RX | **pin 2** — Denon TxD |
| **Sleeve** — GND | **pin 5** — GND |

**Compatible off-the-shelf cable**: StarTech `9M351M-RS232-CABLE` (male DB9 ↔ 3.5 mm jack,
1 m), wired pin 3 → Tip, pin 2 → Ring, pin 5 → Sleeve.

Be careful with generic cables: some use the opposite convention (Tip = DB9 TxD). Check the
datasheet or test continuity with a multimeter. If it is wrong, nothing breaks — it simply
does not communicate; swap Tip and Ring.

If every command comes back unchanged (echo), the jack is not fully inserted.

No hot-plug: connect the cable before powering the dock, or it may brown out.

### Dock 3 configuration

Firmware ≥ 0.10.3. These settings are made in the **dock's web interface**
(`http://<dock-ip>`, with the dock password) — with firmware 0.10.5 the Remote itself does
not offer the RS232 mode:

1. **External port 2** in **RS232** mode (the mode must be forced, not left on Auto).
2. **9600 baud, 8N1.**
3. **"RS232 TCP server (ports 4999, 5000)" enabled.** This is a separate checkbox, off by
   default: without it, port 5000 stays closed even with the port in RS232 mode.
4. Terminator: `13` (CR) or immediate chunk mode — the driver reassembles frames itself,
   both work.

Quick test without the driver, from a terminal on your computer:

```
nc <dock-ip> 5000
PW?          ← type, then Enter
PWSTANDBY    ← answer from the Denon (or PWON)
```

If nothing comes back: swap Tip/Ring, check that port 2 is in RS232 mode at 9600 baud, and
that the TCP server is enabled.

## Running the driver

### On the Remote (custom integration)

Download `uc-intg-denon_rs232-<version>-aarch64.tar.gz` from the
[releases](../../releases), then web configurator → Integrations → Add → Install custom
integration → upload the archive. Or use the
[Integration Manager](https://github.com/JackJPowell/uc-intg-manager).

When updating, the Remote removes and reinstalls the driver: run the setup again, then
**restart the Remote** — otherwise the select entities may show no options.

### Docker

```bash
git clone <this-repo> && cd uc-integration-denon-rs232
mkdir -p config
docker compose up -d --build
docker compose logs -f
```

`network_mode: host` is required for the Remote to discover the driver via mDNS. If your
Docker host does not allow it (Synology, Windows), set `UC_DISABLE_MDNS_PUBLISH=true`,
expose port 9092 and add the integration manually on the Remote with
`http://<docker-ip>:9092`.

The `./config` folder keeps the configuration (`config.json`) across restarts.

### Locally (development)

```bash
pip install -r requirements-dev.txt
cd intg-denon && UC_CONFIG_HOME=../config python driver.py
```

## Setup on the Remote

Integrations → Add → *Denon AV receivers & processors (RS-232)* → fill in:

- Name
- Bridge IP address (the **dock's** address, not the Denon's)
- TCP port: `5000` (dock external port 2 — see above)
- `PW?` check: when ticked, the setup refuses to save if the Denon does not answer within
  4 s. Untick to save anyway (e.g. wiring to be finished later).

## Customising

Everything is declarative, in two files:

- **Sources / modes / parameters**: `intg-denon/denon_control/const.py`
  (`SOURCES`, `SURROUND_MODES`, `ROOM_EQ_MODES`…). Removing an entry from `SOURCES` removes
  it from the media player list, the select, the UI page and the simple commands.
- **Entities**: `intg-denon/const.py` (`SELECTS`, `SWITCHES`, `SENSORS`). One line per entity.

### Simple commands and pass-through

The Remote entity exposes names such as `SOURCE_DVD`, `SURROUND_7CH_STEREO`,
`ROOM_EQ_AUDYSSEY`, `DYN_VOL_EVE`, `QUICK1`, `ZONE2_ON`. In an activity's "Send command",
anything starting with a known Denon prefix (`PS`, `CV`, `MS`, `Z2`…) is sent **as is**:

```
PSSB:MTRX ON
CVFL 505
raw:MNMEN ON
```

## Tests

```bash
pytest                                   # 60 tests: parser (replays a real capture), transport, end-to-end
python tests/denon_simulator.py 5000     # fake Denon over TCP, to test the Remote without hardware
```

The simulator reproduces the behaviour observed on the real unit: `MVMAX 98` after every
`MV`, `MSQUICK1`, state burst after `PWON`, fragmented frames, silence in standby,
`PSDYNSET` ignored unless Dynamic Volume is on.

## Protocol details handled

Observed on a real RS-232 capture and covered by tests:

- Replies split across two reads (`CVFL` … ` 405\r`) — reassembled on CR.
- `MVMAX 98` follows every `MV`: it is the maximum, not the volume.
- `MSQUICK1` has the `MS` prefix but is not a surround mode.
- `SVDVD` / `SVSOURCE` are the video assignment, not the source.
- Irregular PS separators: `PSROOM EQ:AUDYSSEY`, `PSCINEMA EQ.ON`, `PSDSX ONH`.
- `PSDYN VOL` is the Dynamic EQ parameter (value `VOL`), not to be confused with `PSDYNSET`.
- After `MVUP`, the unit reports the old then the new value — updates are debounced.
- Some queries never get an answer (`PSNIGHT ?`, `PSTONE DEFEAT ?`) — the architecture is
  fully event-driven, no command waits for a reply.
- 4 s of silence required after `PWON` (protocol note K), followed by a full refresh.

### "3D upgrade" protocol

The driver follows Denon protocol **6.0.2** of the upgraded AVP-A1HD (November 2011
"3D upgrade"), verified on the real unit:

- Dynamic EQ / Dynamic Volume = **a single parameter** `PSDYN OFF|ON|VOL`
  (`ON` = Dynamic EQ only, `VOL` = Dynamic EQ + Dynamic Volume), level `PSDYNSET DAY|EVE|NGT`.
- Added: Audyssey DSX `PSDSX OFF|ONH|ONW`, stage width/height `PSSTW` / `PSSTH`,
  reference level `PSREFLEV 0|5|10|15`, Dolby PLIIz `PSFH:ON|OFF` and `PSPHG LOW|MID|HI`.
- **Night mode removed** by the upgrade: `PSNIGHT` no longer exists.

## Credits

Structure inspired by [uc-integration-lumagen](https://github.com/johncarey70/uc-integration-lumagen)
(John Carey, MPL-2.0) and built on [ucapi-framework](https://github.com/JackJPowell/ucapi-framework)
(Jack Powell). Dock 3 serial bridge: [ucd3-firmware PR #72](https://github.com/unfoldedcircle/ucd3-firmware/pull/72).

License: MPL-2.0.
