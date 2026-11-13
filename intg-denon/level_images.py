"""Level pictures for the Remote: SVG bars drawn from a number entity's value.

The Remote shows a sensor value as rich text, and its text widget renders ``<img src=...>`` from an
http address, SVG included. A level sensor's value is therefore a picture of the level, served by
this module; the address carries the value, so each change of level is a new picture. The page is
never rewritten (a page change would send the Remote back to page 1 of a multi-page activity).

The integration runs on the Remote, next to its user interface, so the pictures are served on the
loopback address by default. ``DENON_IMAGE_HOST`` / ``DENON_IMAGE_PORT`` change the address the
pictures are announced on and the port (for a driver that runs on another machine).
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import parse_qs, urlsplit

from const import NUMBER_BY_ID, NumberConfig

_LOG = logging.getLogger(__name__)

# 8000-9200 are reserved on the Remote; other custom integrations use 9300-9320
# (IPTV, OPPO Music, Emby)
DEFAULT_PORT = 9330
PORT_TRIES = 10  # the next ports are tried when one is taken
BLUE = "#4da6ff"
TRACK = "#2b2b2b"
GREY = "#8a8a8a"
FONT = 'font-family="Poppins, sans-serif"'

# Picture sizes, fitted to the widgets they were designed for (a little narrower than the widget:
# the Remote appends a space after the value).
CARD_SIZE = (136, 96)  # volume: a 2x3 tile of a 6x12 page
BAR_SIZE = (216, 50)  # other levels: a 2x1 tile of a 4x7 page


def _number(value: float, signed: bool) -> str:
    if signed:
        return "0.0" if value == 0 else f"{value:+.1f}"
    return f"{value:.1f}"


def level_card(cfg: NumberConfig, value: float) -> str:
    """Large value with its unit, a thin bar filling from the minimum (master volume)."""
    w, h = CARD_SIZE
    th = 16
    x0, span = 6, w - 12
    y = h - th - 4
    clamped = min(max(value, cfg.minimum), cfg.maximum)
    fill = max(span * (clamped - cfg.minimum) / (cfg.maximum - cfg.minimum), th)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<text x="{w / 2}" y="{y - 16}" text-anchor="middle" {FONT} font-size="38" fill="{BLUE}">'
        f'{_number(value, False)}<tspan font-size="18" fill="{GREY}"> dB</tspan></text>'
        f'<rect x="{x0}" y="{y}" width="{span}" height="{th}" rx="{th / 2}" fill="{TRACK}"/>'
        f'<rect x="{x0}" y="{y}" width="{fill:.1f}" height="{th}" rx="{th / 2}" fill="{BLUE}"/>'
        "</svg>"
    )


def level_bar(cfg: NumberConfig, value: float) -> str:
    """A bar filling from 0 dB to the value, the value written inside (channel levels, tone)."""
    w, h = BAR_SIZE
    th = 46
    x0, span = 3, w - 6
    y = (h - th) / 2
    origin = min(max(0.0, cfg.minimum), cfg.maximum)

    def pos(val: float) -> float:
        val = min(max(val, cfg.minimum), cfg.maximum)
        return x0 + (val - cfg.minimum) / (cfg.maximum - cfg.minimum) * span

    a, b = sorted((pos(origin), pos(value)))
    fill = ""
    if b - a > 0.5:
        fill = f'<rect x="{a:.1f}" y="{y}" width="{b - a:.1f}" height="{th}" fill="{BLUE}"/>'
    mark = ""
    if cfg.minimum < origin < cfg.maximum:
        mark = (
            f'<rect x="{pos(origin) - 1:.1f}" y="{y}" width="2" height="{th}" '
            'fill="#ffffff" opacity="0.5"/>'
        )
    signed = cfg.minimum < 0 < cfg.maximum
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><clipPath id="c"><rect x="{x0}" y="{y}" width="{span}" height="{th}" '
        f'rx="{th / 2}"/></clipPath></defs>'
        f'<rect x="{x0}" y="{y}" width="{span}" height="{th}" rx="{th / 2}" fill="{TRACK}"/>'
        f'<g clip-path="url(#c)">{fill}{mark}</g>'
        f'<text x="{w / 2}" y="{y + th / 2 + 10}" text-anchor="middle" {FONT} font-size="28" '
        f'fill="#ffffff" stroke="#000000" stroke-width="0.8" paint-order="stroke">'
        f'{_number(value, signed)} <tspan font-size="18">dB</tspan></text></svg>'
    )


def draw(number_id: str, value: float) -> str:
    """The picture of one number entity's level."""
    cfg = NUMBER_BY_ID[number_id]
    return level_card(cfg, value) if cfg.kind == "volume" else level_bar(cfg, value)


def picture_size(number_id: str) -> tuple[int, int]:
    return CARD_SIZE if NUMBER_BY_ID[number_id].kind == "volume" else BAR_SIZE


class LevelImageServer:
    """Minimal HTTP server: GET /level/<number id>.svg?v=<value> returns the picture."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.port = port or int(os.getenv("DENON_IMAGE_PORT", str(DEFAULT_PORT)))
        self.host = host or os.getenv("DENON_IMAGE_HOST", "127.0.0.1")
        self._server: asyncio.base_events.Server | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def url(self, number_id: str, value: float) -> str:
        return f"http://{self.host}:{self.port}/level/{number_id}.svg?v={value:.1f}"

    def img(self, number_id: str, value: float) -> str:
        """Rich text for a sensor value: the picture of the level."""
        w, h = picture_size(number_id)
        return f"<img src='{self.url(number_id, value)}' width='{w}' height='{h}'>"

    async def start(self) -> None:
        first = self.port
        for port in range(first, first + PORT_TRIES):
            try:
                self._server = await asyncio.start_server(self._handle, "0.0.0.0", port)
            except OSError as ex:
                _LOG.info("Level pictures: port %s unavailable (%s)", port, ex)
                continue
            self.port = port
            _LOG.info("Level pictures served on port %s (announced as %s)", port, self.host)
            return
        self._server = None
        last = first + PORT_TRIES - 1
        _LOG.warning("Level pictures not served: ports %s-%s unavailable", first, last)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readline(), 5)
            while (await asyncio.wait_for(reader.readline(), 5)) not in (b"\r\n", b"\n", b""):
                pass
            status, body, ctype = self.respond(request.decode("latin-1"))
            head = (
                f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
                "Cache-Control: max-age=86400\r\nConnection: close\r\n\r\n"
            )
            writer.write(head.encode() + body)
            await writer.drain()
        except (TimeoutError, ConnectionError, UnicodeDecodeError):
            pass
        finally:
            writer.close()

    @staticmethod
    def respond(request_line: str) -> tuple[str, bytes, str]:
        """(status, body, content type) for one request line: pure, tested without a socket."""
        parts = request_line.split()
        if len(parts) < 2 or parts[0] != "GET":
            return "405 Method Not Allowed", b"", "text/plain"
        url = urlsplit(parts[1])
        name = url.path.rsplit("/", 1)[-1].removesuffix(".svg")
        if not url.path.startswith("/level/") or name not in NUMBER_BY_ID:
            return "404 Not Found", b"", "text/plain"
        try:
            value = float(parse_qs(url.query).get("v", ["nan"])[0])
        except ValueError:
            value = float("nan")
        if value != value:  # NaN: missing or not a number
            return "400 Bad Request", b"", "text/plain"
        return "200 OK", draw(name, value).encode(), "image/svg+xml"


SERVER = LevelImageServer()
