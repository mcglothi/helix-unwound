# Truck checklist: Measure this seat + time alignment

Last Updated: 2026-10-29

First run of both workflows with sound. Both write mutes and delays to the DSP's working
memory (never flash), so only run them with Tim in the truck. A power cycle returns the DSP to
its stored preset.

## Before you go out

1. Phone: copy `~/Downloads/helixtune-pink-noise-20dBFS.wav` over and open it in VLC for
   Android. Turn on repeat-one. To regenerate it: `.venv/bin/python scripts/make_pink_noise.py`.
2. Mac: start REW 5.40 beta with its API: `open -a /Applications/REW/REW.app --args -api`.
3. In REW, plug in the UMIK-1, pick it as the input, and check that the **90°** calibration file
   (serial 7015199) is loaded.
4. In REW, **open the RTA window and leave it open.** REW only listens while it is open.
5. Bring the USB-C hub and USB cable, with the Mac charged.

## In the truck: set up

1. **Read Digital Volume on the Director** (Menu → Unused Functions → Digital Volume) and note it.
   It should be 0 dB.
2. Phone on AAWireless/Android Auto. Turn on Do Not Disturb, phone EQ off, Spotify normalization
   off. Keep the volume low for now.
3. Plug the Mac into the Helix by USB. In `~/code/helix-dsp`, run:
   - `uv run helixtune serve --allow-physical-writes`
   - then, in a second terminal: `uv run helixtune open`
4. Check that the active scene is your current tune. Connect with writes enabled, review, and type
   **OVERWRITE**. The device should show *synchronized*.
5. Unmute every output you want to measure.

## Run 1: Measure this seat

1. Drive view → **Measure this seat** → *Measure outputs*.
2. Choose *Front drivers*, seat **Driver**, *20 seconds* per output, and **"I'll play it from my
   phone"**.
3. Start the pink noise on the phone. Raise the volume until it is clearly louder than the cabin
   noise, at a level you could listen to comfortably.
4. Press Start. Sit still and move the mic slowly around your head, about a hand's width each way,
   **pointing up** (that is what the 90° file is for).
5. When it finishes, the outputs should all be unmuted again and the captures should show in
   Measurements.

## Run 2: Time alignment (one crossover pair at a time)

1. Measure this seat → **Time alignment**. Hold the mic **still** at your head, pointing up.
   Settings: seat Driver, 9 steps, 6 s per step (about 2–3 min per pair), phone noise playing.
2. Suggested order, one side at a time (check the letters against your tune's names):
   1. tweeter to mid: reference C, adjust E;
   2. mid to midbass: reference A, adjust C, and **move E with it**;
   3. repeat with B/D/F for the right side.
   The dialog refuses pairs without a shared crossover.
3. Each run ends with a **proposal**. Nothing changes until you review and apply it.
   - If a flipped polarity wins, check that speaker's wiring before applying.
   - If the run says the signal is too close to the floor, raise the volume and run it again.

## Wrap up

1. Stop the noise on the phone. Disconnect in the UI, then press Ctrl-C on `serve`.
2. **Read Digital Volume again**. It should still be 0 dB. Confirm normal audio from the phone.
3. Tell Claude how each run ended (proposals, any refusals or errors).
