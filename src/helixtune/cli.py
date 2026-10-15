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
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"WARNING: listening on {args.host} — anyone on this network can change the tune")
    uvicorn.run(create_app(eng), host=args.host, port=args.port, log_level="warning")
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
    s = sub.add_parser("serve", help="run the engine, HTTP API and web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--data", default="~/.helixtune")
    s.add_argument("--at01")
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("mcp", help="MCP stdio server (talks to a running `serve`)").set_defaults(fn=cmd_mcp)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
