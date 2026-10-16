# Community tuning and DSP usability research

Last Updated: 2026-10-15

Tim's explicit product requirement: study successful tuning practice **and what
people dislike about DSP software**, including overall UI/UX. Modern appearance,
clear workflows, predictable behavior and recovery are core product work. This is
an initial source notebook, not a representative survey or a vendor ranking.

## Source observations

1. [SkizeR: DSP Tuning Using REW — A Basic Starters Guide, CarAudio.com (2017)](https://www.caraudio.com/threads/dsp-tuning-using-rew-a-basic-starters-guide.593662/).
   The author describes an isolated-output workflow followed by paired-output
   checks, remeasurement and listening. It is explicitly a beginner method with
   crossover/time-alignment prerequisites. Product implication: show which outputs
   a capture covers and make verification a visible next step. Do not translate
   this particular method's crossover settings into universal defaults.

2. [JBL DSP4086 Software unresponsive, r/CarAV (2023)](https://www.reddit.com/r/CarAV/comments/15kf45b/jbl_dsp4086_software_unresponsive/).
   Firsthand report of frozen software, including a follow-up that freezing also
   happened without the amplifier attached. It does not establish a root cause or
   failure rate. Product implication: useful offline editing/demo operation,
   responsive progress/errors, and distinct connection/write/sync states.

3. [Alpine PXA-H800 troubleshooting thread, CarAudio.com](https://www.caraudio.com/threads/i-am-so-alomst-done-with-this-alpine-pxa-h800-dsp-pos.591966/).
   Search results surfaced device-discovery/connection frustration. Full relevant
   pages could not be retrieved reliably in this pass. Treat as a research lead,
   not verified evidence of a driver bug or a specific product defect.

4. [DIYMobileAudio: First Timer's Guide to Measuring Your System](https://www.diymobileaudio.com/threads/first-timers-guide-to-measuring-your-system.163234/).
   Searches targeted DIYMA tuning, moving-microphone and gain-structure posts.
   Direct thread retrieval failed; no technical conclusion has been attributed
   to its contents. Revisit through ordinary public browser access when available.
   Do not replace unread primary posts with search snippets or third-party summaries.

5. [REW official API documentation](https://www.roomeqwizard.com/help/help/html/api.html)
   and [measurement documentation](https://www.roomeqwizard.com/help/help_en-GB/html/makingmeasurements.html).
   Primary technical checks for read-only integration, stable IDs, frequency data
   and timing/clock limitations. Community workflow preferences are distinguished
   from these API/measurement requirements.

## Acceptance criteria derived for Helix Unwound

| User problem / research question | Product requirement | Current evidence / remaining work |
|---|---|---|
| “Is it connected, and did it actually send my tune?” | Separate offline, read-only, ready-to-send, sending and recovery states. No silent overwrite on connect. | Connection panel + context-bound review; API and emulator regressions. Independent hardware readback still unverified. |
| “It froze; did I lose my work?” | Maintain useful offline editing; preserve accepted tune on failed device writes; show recovery without claiming a hardware rollback. | Atomic tune/history/A-B checkpoint plus previous-checkpoint recovery and visible save failures; device-write regressions and isolated restart demo. Independent equipment/measurement transactions remain open. |
| “What does this button change?” | Outcome-based labels, local scene vs device actions distinguished, extra protocol detail disclosed progressively. | New connection review uses a named tune and explicit send confirmation; broad labeling audit remains. |
| “Why is the graph convincing when the measurement is unsuitable?” | Show sources, missing coverage and refusal reasons; do not label combined captures as individual drivers. | Evidence-aware estimate view already implemented. |
| “I have to keep copying filters and measurements between applications.” | Browse/preview/copy REW captures without altering source data or silently assigning current hardware. | Read-only REW adapter with fixture tests; live REW acceptance pending. |
| “Can I fix a mistake?” | Predictable Undo, explicit scene overwrite, retained review conflicts; no automatic dismissal on failure. | Durable Undo/Redo with protection rechecks, scene/A-B final-state checkpoints and rendered edit/Undo/Redo/restart verification. |
| “Desktop software on my phone is unusable.” | Responsive layouts, readable status, large targets, keyboard/focus support, no hidden primary action. | Dialog viewport bounds/progressive disclosure; phone and full accessibility testing remain pending. |

## Research continuation

Seek concrete firsthand posts/screenshots about small or fixed-size controls,
confusing channel linking, input/output routing, local-file vs device-preset saves,
copy/paste filters, opaque errors, unsaved work, disconnections, platform support,
color/contrast and keyboard access. Include positive counterexamples. Record model,
software version/date, source, reproducible trigger and desired outcome. Separate
reported symptoms from verified causes; do not generalize one old post into market
consensus. Exclude Line 6 guitar Helix results from car-DSP searches.

The notebook changes product acceptance criteria; it does not authorize automated
crossover values, driver limits, measurement excitation or hardware writes.
