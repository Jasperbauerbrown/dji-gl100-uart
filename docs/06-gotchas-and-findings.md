# 06 — Gotchas & findings

Hard-won, non-obvious behaviours.

## Watchdog: never `kill -STOP apsrv`

`apsrv` pets a watchdog. If you `kill -STOP` / `killall -STOP apsrv` (e.g. to silence the console
flood), the watchdog fires a **full system reset after ~30–60 s**. Worse, a **watchdog reset
leaves the AR6006 USB wifi un-enumerated** (see below). So:

- To quiet the console for a long operation, **do not stop apsrv** — tolerate the flood and filter
  host-side (see `docs/04`). Lower kernel noise with `echo 0 > /proc/sys/kernel/printk` only.

## AR6006 (softAP / `wlan1`) USB enumeration is fragile

The softAP radio is a **USB** device (QCA6006X → `ath6kl_usb`) behind the GL850 hub. It enumerates
reliably only on a clean **cold power-up** of a fully-assembled, adequately-charged unit. When it
fails you'll see, repeatedly, in `dmesg`:

```
usb 1-1.1: device descriptor read/64, error -32
usb 1-1.1: device not accepting address N, error -32
hub 1-1:1.0: unable to enumerate USB device on port 1
```

Observed triggers for the failure: partial reassembly (gimbal/daughter boards disconnected),
**low battery / marginal USB power**, a disturbed board-to-board connection, and **after a
watchdog reset** (vs. a clean cold boot). `error -32` (`-EPIPE`) here is a physical/signal/power
problem — **there is no software fix**. If `wlan1` won't come up: fully reassemble, charge, and
cold-boot; otherwise just use the serial console (you don't need wifi to dump or reflash).

## Auto power-off (sleep) is MCU-side

The RC powers itself off after a period of **no stick/button activity** (bumping a stick resets
it). This timer lives in the **STM32F051 MCU**, which reads the sticks directly — **not** in Linux:

- No OpenWrt/UCI config knob for it.
- `apsrv` has no auto-power-off setter; it only relays to the MCU.
- `/etc/rc.button/power` simply runs `/sbin/poweroff` on a power-button event.

So disabling sleep means reaching the MCU — e.g. sending DJI's "auto power off = never" **DUML**
command (the toggle the DJI app exposes) to the MCU, or modifying the STM32 firmware. The STM32
firmware is **not** in the SPI dump (it lives in the MCU's internal flash; `fw_mcu.bin` is only an
update file), so MCU-side work needs SWD or a captured update image. *(Still open.)*

Open question worth testing on your own unit: whether the MCU triggers sleep by *signalling a
power-button event to Linux* (→ `/etc/rc.button/power` → `/sbin/poweroff`) or by *cutting power in
hardware*. If the former, neutering `/sbin/poweroff` (RAM-only test first) would block it; if the
latter, only the MCU route works.

## U-Boot serial abort disabled

Covered in `docs/02`: the `Press S to abort autoboot` prompt is vestigial — DJI removed the serial
key-check. Don't waste time stream-spamming keys at boot; log in to Linux instead.

## LZMA props byte 0x6d

Covered in `docs/05`: the kernel LZMA uses a non-standard properties byte (`0x6d`, not `0x5d`) and
an 8 MB dictionary. Tools that hard-check for `5D 00 00` will refuse the payload; feed it to a
decoder that parses the LZMA-alone header itself.

## No USB-device mode, ever

Covered in `docs/01`: the AR9342 is host-only; nothing on the board can be a PC-facing USB device.
Don't chase making the RC enumerate to a PC — it's a silicon limitation.
