# Windows capture checklist (Dell + PC-Tool 4.80b)

Goal: record the original PC-Tool talking to the DSP PRO MK2 so every provisional
assumption in `src/helixtune/mapping.py` and `protocol/` can be confirmed or fixed.

## Safety first
- **Amps off** (or speaker outputs disconnected) for every capture. A wrong write
  must not be able to reach a speaker.
- Do **not** run any firmware update in PC-Tool.

## Setup
1. Win11, all updates done.
2. Install PC-Tool 4.80b from the same installer (`Setup_ATF_DSP_PC-TOOL_4-80b.exe`).
   When it offers drivers, install the FTDI driver.
3. Install **Wireshark** and tick **USBPcap** during setup. Reboot.
4. Plug the DSP in, power it from a 12 V bench supply or the truck.
5. Device Manager → Ports: note the COM port and, under Details → Hardware Ids,
   the `VID_xxxx&PID_xxxx`. Write those down.

## How to capture each step
- Start Wireshark → pick the `USBPcap` interface the DSP is on (try each; the right
  one shows traffic when PC-Tool connects) → start.
- Do **one** action from the list below.
- Stop, then **File → Save As** `NN-name.pcapng`. One action per file.
- Write in `notes.txt` exactly what you did, including values (e.g. "ch A band 1
  1000 Hz → +3.0 dB, Q 1.4, peak").

## Steps
| # | file | action |
|---|------|--------|
| 01 | 01-connect.pcapng | Start capture, then open PC-Tool and let it connect. Stop once it shows the main screen. |
| 02 | 02-idle.pcapng | 10 s of doing nothing (shows any keep-alive / live meters). |
| 03 | 03-save-preset.pcapng | Save the current setup to a file (`my-truck.afpx`). **Keep this file — it's your current tune.** |
| 04 | 04-eq-a-band1.pcapng | Channel A, EQ band 1: change gain only, by +3 dB. |
| 05 | 05-eq-a-band1-freq.pcapng | Same band: change frequency only. |
| 06 | 06-eq-b-band1.pcapng | Channel **B**, band 1, +3 dB (proves the EQ block ↔ channel mapping). |
| 07 | 07-eq-a-band16.pcapng | Channel A, band 16, +3 dB (second EQ block). |
| 08 | 08-hp-a.pcapng | Channel A high-pass: change frequency only. |
| 09 | 09-hp-a-slope.pcapng | Channel A high-pass: change slope only (e.g. 12 → 24). |
| 10 | 10-lp-a.pcapng | Channel A low-pass: change frequency only. |
| 11 | 11-delay-a.pcapng | Channel A delay: change by a small amount. |
| 12 | 12-gain-a.pcapng | Channel A level: −3 dB. |
| 13 | 13-mute-a.pcapng | Mute channel A, then unmute. |
| 14 | 14-invert-a.pcapng | Invert channel A phase, then back. |
| 15 | 15-master.pcapng | Master volume down then up. |
| 16 | 16-load-preset.pcapng | Load `my-truck.afpx` back into the DSP. |
| 17 | 17-disconnect.pcapng | Close PC-Tool. |

## Preset decoding (no captures needed)
Copy `captures/backups-2018/Helix Presets/*.afpx` to the Dell. For
`BasicTune - DRV-TA.afpx` and `BasicTune - PAS-TA.afpx`: load the preset in PC-Tool
(with or without the DSP connected) and screenshot, for every used channel, the
crossover/EQ screen, the delay/time-alignment screen (with units shown — ms and cm),
and the phase control. Also screenshot the routing matrix and channel-name assignments.
These screenshots let us decode the remaining preset fields exactly.

Afterwards, put back any settings you changed (or load `my-truck.afpx`).
Copy the `.pcapng` files, `notes.txt`, `my-truck.afpx` and a few screenshots of the
channel/EQ/crossover screens into `~/code/helix-dsp/captures/` on the Mac.
