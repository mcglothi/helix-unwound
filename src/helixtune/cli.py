"""helixtune CLI. `probe` is read-only: it sends only the identify command."""

from __future__ import annotations

import argparse
import sys

from .protocol import commands
from .protocol.client import Client

FTDI_VID = 0x0403
ATF_VID = 0x2E4F


def list_candidate_ports():
    from serial.tools import list_ports

    ports = []
    for p in list_ports.comports():
        if p.vid in (FTDI_VID, ATF_VID) and not p.device.startswith("/dev/tty."):
            ports.append(p)
    return ports


def cmd_ports(_args) -> int:
    from serial.tools import list_ports

    for p in list_ports.comports():
        vid = f"{p.vid:04x}:{p.pid:04x}" if p.vid is not None else "----:----"
        print(f"{p.device:32} {vid}  {p.description}  serial={p.serial_number}")
    return 0


def cmd_probe(args) -> int:
    import serial

    port = args.port
    if not port:
        cands = list_candidate_ports()
        if len(cands) != 1:
            print(f"found {len(cands)} FTDI/ATF ports; pass --port. Run `helixtune ports` to see all.")
            return 2
        port = cands[0].device
    print(f"probing {port} at {commands.LOW_HOST_BAUD} 8N1 (identify only, no writes)")
    with serial.Serial(port, commands.LOW_HOST_BAUD, bytesize=8, parity="N", stopbits=1,
                       rtscts=False, xonxoff=False, timeout=0.05) as ser:
        try:
            info = Client(ser, timeout=args.timeout).identify()
        except (TimeoutError, ValueError) as e:
            print(f"no valid reply: {e}")
            return 1
    print(f"reply payload ({len(info.raw)} bytes):")
    for i in range(0, len(info.raw), 16):
        chunk = info.raw[i : i + 16]
        asc = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        print(f"  {i:04x}  {chunk.hex(' '):47}  {asc}")
    print(f"model string: {info.model_string!r}  type: {info.model_type}")
    if info.model_type == commands.PRO_MK2:
        print("=> HELIX DSP PRO MK2 detected")
    return 0


def cmd_backup_stored(args) -> int:
    """Explicit port and output required; no auto-discovery, session or baud switch."""
    import serial
    from pathlib import Path
    from . import stored_preset
    target = Path(args.output).expanduser()
    if not target.parent.is_dir():
        print("Backup parent directory does not exist; no port opened", file=sys.stderr)
        return 2
    if target.exists():
        print("Backup destination already exists; choose a new file (nothing overwritten)", file=sys.stderr)
        return 2
    try:
        with serial.Serial(args.port, commands.LOW_HOST_BAUD, bytesize=8, parity="N", stopbits=1,
                           rtscts=False, xonxoff=False, timeout=0.05) as transport:
            client = Client(transport, timeout=1)
            if client.identify().model_type != commands.PRO_MK2:
                raise ValueError("Connected device was not identified as DSP PRO MK2")
            preset = stored_preset.read(client)
        stored_preset.save(target, preset)
    except TimeoutError:
        print("Read timed out. No session/baud fallback was attempted; 19200-baud stored reads need live validation.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Stored-preset backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Stored preset backed up to {target} ({len(preset.blob)} bytes, SHA256 {preset.sha256}).")
    print(f"XML SHA256 {preset.xml_sha256}")
    print("This backs up stored XML, not unsaved current RAM. No preset was selected, loaded or written.")
    return 0


def find_param_map(explicit: str | None):
    import os
    from pathlib import Path

    cands = [explicit, os.environ.get("HELIXTUNE_AT01"),
             Path.home() / ".helixtune" / "DSPPro2.at01",
             Path(__file__).resolve().parents[2] / "artifacts/extracted/app/deviceFiles/DSPPro2.at01"]
    for c in cands:
        if c and Path(c).exists():
            return Path(c)
    raise SystemExit("DSPPro2.at01 not found; pass --at01 or copy it to ~/.helixtune/ "
                     "(it ships in the PC-Tool installer's deviceFiles/)")


def cmd_serve(args) -> int:
    from pathlib import Path

    import uvicorn

    from .api import create_app
    from .devicefile import load_at01
    from .engine import Engine

    eng = Engine.from_param_map(load_at01(find_param_map(args.at01)), Path(args.data).expanduser())
    print("Owner UI: run 'helixtune open' in another terminal (use matching --data/--port).")
    if args.host not in ("127.0.0.1", "localhost"):
        print("Remote access requires credentials. Use a trusted network or an encrypted tunnel for HTTP.")
    uvicorn.run(create_app(eng), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_demo(args) -> int:
    from pathlib import Path
    import uvicorn
    from .api import create_app
    from .demo import create_demo_engine
    from .engine import EngineError
    try:
        engine = create_demo_engine(Path(args.data))
    except (EngineError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    print("DEMO: invented hardware and measurements; physical device connections are disabled.")
    import shlex
    print(f"Owner UI: helixtune open --data {shlex.quote(str(engine.data_dir))} --port {args.port}")
    uvicorn.run(create_app(engine), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_open(args) -> int:
    from pathlib import Path
    from urllib.parse import urlencode
    import webbrowser

    from .access import read_token

    # The fragment is never sent in HTTP requests; the UI removes it immediately
    # and exchanges it for an HttpOnly session. Never print the credential URL.
    token = read_token(Path(args.data).expanduser(), "owner")
    url = f"http://127.0.0.1:{args.port}/#" + urlencode({"token": token})
    if not webbrowser.open(url):
        print("Could not open a browser; open the local UI and use the owner credential from the data directory.")
        return 1
    return 0


def cmd_mcp(_args) -> int:
    from .mcp_server import main as run

    run()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="helixtune")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports", help="list serial ports").set_defaults(fn=cmd_ports)
    p = sub.add_parser("probe", help="read-only identify of a connected DSP")
    p.add_argument("--port")
    p.add_argument("--timeout", type=float, default=1.0)
    p.set_defaults(fn=cmd_probe)
    backup = sub.add_parser("backup-stored", help="explicit read-only stored-preset backup at 19200 baud")
    backup.add_argument("--port", required=True)
    backup.add_argument("--output", required=True, help="new .afpx file; never overwritten")
    backup.set_defaults(fn=cmd_backup_stored)
    s = sub.add_parser("serve", help="run the engine, HTTP API and web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--data", default="~/.helixtune")
    s.add_argument("--at01")
    s.set_defaults(fn=cmd_serve)
    d = sub.add_parser("demo", help="hardware-free workstation with synthetic example data")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8770)
    d.add_argument("--data", default="~/.helixtune-demo")
    d.set_defaults(fn=cmd_demo)
    o = sub.add_parser("open", help="open the local owner UI without printing credentials")
    o.add_argument("--data", default="~/.helixtune")
    o.add_argument("--port", type=int, default=8765)
    o.set_defaults(fn=cmd_open)
    sub.add_parser("mcp", help="MCP stdio server (talks to a running `serve`)").set_defaults(fn=cmd_mcp)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
