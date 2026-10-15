# Helix DSP PRO MK2 — RE Findings

Last Updated: 2026-10-15

Target: `Setup_ATF_DSP_PC-TOOL_4-80b.exe` (Inno Setup 6.1)
- installer sha256 `ae3ba71f348870cb6322f9f541d01783a74607e1c09ca8c0135c820120e3bcd2`
- `ATF_DSP_PC-TOOL.exe` sha256 `a67a10d5eca96e1b6519742a77e83cc67ea8741dc0546050fdaa8b7fa6c83ef1`
- Extracted with `innoextract` (no execution) → `artifacts/extracted/app/`

## Observed (static)

### App stack
- 32-bit x86 PE, Qt 5 + MinGW (libgcc_s_dw2, libstdc++-6). Qt moc metadata and RTTI
  names survive (`HelixDSPPRO`, `HelixDSPPROMK2`, `HelixDSPPROMK3`, slot/signal sigs).
- All device I/O goes through `QSerialPort` (Qt5SerialPort.dll). No HID/WinUSB/libusb/ftd2xx.
- Also links Qt5Bluetooth, Qt5Network (WiFi control on newer units; `netConf.txt` = `OFF`).

### Transport
- Newer devices: CDC-ACM via `usbser.sys`, VID `0x2E4F` (Audiotec Fischer), PIDs 0x2000–0x3006.
  **DSP PRO MK2 is not in that INF** → older units use FTDI VCP (strings: "Install FTDI
  USB-Driver", "open COM new MC FTDI"). macOS ships AppleUSBFTDI → `/dev/cu.usbserial-*`.
- Comms classes/slots: `uartbuffer`, `mcFrameBuffer`, `enqUartData`, `add4trans`,
  `sendConQueue(int,int)`, `setHighBaud/setLowBaud(+WOQ)`, `setBaudrateMode(int)`,
  `connectionOK(bool)`, `emitNewMC(bool)` ("New uC detected"), `sendReadback(int,QByteArray)`,
  `sendLiveMonData`, `sendAfpReadBuf`.
- Errors hint at write rules: "no writing in RAM Addr 0 allowed", "Can't Write in wrong SW
  Version", "Can't send to device without DevParam", "DM1 Pack! Error".

### DSP core
- `.AF1` = hex text, header `$VR1`, starts with register writes 0xF890/0xF400… →
  consistent with **ADI SigmaDSP ADAU145x** control registers (inference; confirm chip).
- `.at01` = Qt `qCompress` (4-byte BE length + zlib) of a SigmaStudio-exported
  parameter header. DSPPro2: 2,864 `#define`s — DM0ADD 0, DM1ADD 44768, safeload at 6180–6186.
  Modules: EQUALIZER (1500), FILTERS (410), URC, MAINMATRIX (144), INPUT, LIMITER A–I,
  DELAY, OUTPUT, SUB, AUX, OPTO, MUTE A–J, MASTERVOLUME, GAIN.
  Decoded copy: `notes/DSPPro2.at01.dec`.
- ⇒ The PC tool computes biquad coefficients host-side and writes them to DSP parameter
  RAM through the microcontroller (inference; framing still unknown).

### Profiles
- Presets: `*.afpx` (current), `*.afp` (previous); REW Generic EQ import supported.
- Password-protected profiles use a hardcoded string in the binary (not reproduced here).

## Wire protocol (decompiled — REA/Ghidra, unverified on hardware)

Serial: 8N1, no flow control, opened at **19200** (`FUN_0075d0e0(0x4b00)`); high/low baud
switch exists (rate not yet extracted). FTDI ("new MC") and CDC paths share the framing.

TX frame (`FUN_0056c710`, ev_6e33598d…):
```
42 | L=N+1 | ~L | ch | payload[N] | sum8(payload)
```
- `ch` = ctor param_4 (observed = 1 at both call sites).
- Alt "sync" frame when ctor param_1 set: `42 00 42 00 42 00 42 00 42 00` (10 B, 100 ms timeout).
- ⚠ L=N+1 on TX vs n=N on RX is as decompiled; confirm with a capture.

RX frame (`FUN_0056c810`): `43 | n | ~n | ch(must match) | payload[n] | sum8(payload)`

Command payloads (`FUN_00574f40` switch on cmd id; addr = 16-bit BE):
| cmd | payload layout | notes |
|-----|----------------|-------|
| 00/01 | `cmd data…` | |
| 02 | `02 x addrHi addrLo data…` | |
| 03 | `03 x (01/FF) addrHi addrLo data…` | rx 10 |
| 04 | `04 addrHi addrLo len` | likely RAM read |
| 05 | `05 addrHi addrLo len data…` (or `32 05 …` ext form) | likely RAM write, rx 10 |
| 06 | `06 addrHi addrLo len` | |
| 07 | `07 addrHi addrLo len data…` | rx 10 |
| **08** | `08` | **identify/probe, rx 179 B** (`FUN_0075db80`) |
| 09–0E, 10–1D, 28, 32–38 | various, mostly 1–6 B | TBD |

Probe frame (derived, unverified): `42 02 FD 01 08 08`.

Key functions: serial ctor/connect `0x75e5d0`, open `0x75e2b0`, setBaud `0x75d0e0`,
error check `0x75cd30`, probe `0x75db80`, sync xfer `0x75d2e0`, frame ctor `0x56c2e0`,
serialize `0x56c710`, rx validate `0x56c810`, cmd builder `0x575b50`/`0x574f40`,
RAM-write dispatcher `0x50bd60`.

### Baud switching (`FUN_0057b950/bd60/c5f0/c9f0`)
Payload `0A xx`, sent **3×** (200 ms timeout each), then 500 ms sleep, then host reopens:
| payload | host baud after |
|---------|-----------------|
| `0A 03` | 230400 (`setHighBaud`) |
| `0A 03` | 250000 (`setHighBaudWOQ` variant) |
| `0A 2F` | 19200 (`setLowBaud`) |
| `0A 33` | 19200 (`setLowBaudWOQ`, log "workerCOM: setting device baudrate to LOW WOQ") |
Each switch is preceded by a uartbuffer sync step (`FUN_0056c140`) — likely the `42 00 ×5` frame.

### Device identification (`FUN_0051d790`, dispatcher `FUN_0052f520`)
The identify response carries an ASCII model string (devparam+0x60) matched by prefix:
`"2DSP-PRO"` → type **0x0F = HELIX DSP PRO MK2**; `"DSP-PRO"` → 0x06 (PRO); `"DSP3"` → 0x15;
`"DSPULTRA"` → 0x16; `"HELI"` → 0x02; `"V8 D"` → 0x07; `"BRAX-DSP"` → 0x11; etc. (full list in fn).
devparam+0x18 == `'R'` → DSP program present ("Connected 96k"); else "Connected no Software".
Decompiled switch saved at `notes/devtype_switch.c` (gitignored; vendor-derived).

## Unknown (next)
- [ ] Exact byte offsets of model string / 'R' flag inside the 179-byte identify payload
- [ ] Which frames are read-only (identify, readback) vs writes
- [ ] .afpx file format
- [ ] Confirm DSP PRO MK2 USB VID/PID on real hardware (`ioreg -p IOUSB -l`)
