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
it). This timer lives in the **STM32F051 MCU**, **not** in Linux (see the correction below about who reads the sticks):

- No OpenWrt/UCI config knob for it.
- `apsrv` has no auto-power-off setter; it only relays to the MCU.
- `/etc/rc.button/power` simply runs `/sbin/poweroff` on a power-button event.

So disabling sleep means reaching the MCU — e.g. sending DJI's "auto power off = never" **DUML**
command (the toggle the DJI app exposes) to the MCU, or modifying the STM32 firmware. The STM32
firmware is **not** in the SPI dump (it lives in the MCU's internal flash; `fw_mcu.bin` is only an
update file), so MCU-side work needs SWD or a captured update image. *(Still open.)*

**Verified: the MCU cuts power in hardware.** Test: `poweroff`/`halt`/`reboot` were replaced with
logging stubs (RAM only), `printk` was set to EMERG, and a 2 s uptime heartbeat was sent to the
console. The console stopped mid-stream at uptime ≈ 670 s. There was no stub call, no kernel
`Power down`, and no warning line from `apsrv` beforehand. Linux is never told. Neutering
`/sbin/poweroff` does nothing. (`/etc/rc.button/power` is likely dead code anyway: the boot uses
`mdev`, not procd hotplug.)

**Correction:** the sticks are **not** read by the MCU. They are two MLX90393 hall sensors on the
AR9342 SPI bus (`spi0.1`/`spi0.2` → `/dev/input/event0`/`event1`, driver `mlx90393.ko`), and
`apsrv` reads them. `apsrv` is the only process with `/dev/ttyATH0` (the MCU link) open. If the
MCU's idle timer reacts to stick motion, it must be learning about it from `apsrv` over `ttyATH0`.

**Verified software keep-awake (no MCU work needed):** evdev nodes accept `write()`. Writing an
`EV_ABS` event to `/dev/input/event0` reaches every reader, including `apsrv`, which forwards it
to the MCU like a real stick move. A burst of 10 × `ABS_X=+246` (about 2.6°, roughly 10% of the
calibrated ±25° throw) every 30 s kept the RC on for 32+ min, against a ~11 min power-off with no
injection. The sensors' natural jitter (~6 counts, about 0.02°) does **not** count as activity.
Script: [`tools/rc_keepalive.sh`](../tools/rc_keepalive.sh). It is RAM only, so start it after
each boot. ⚠️ It is real stick input: don't run it with an aircraft linked.

Stick scale: raw X/Y around ±450 at center and Z around −15300. The angle is roughly
`atan(x/z)` (matches `mid_x`/`mid_y` in `/etc/amt/cali_stick_*.txt`), so full throw is about
±7000 raw counts.

Still open: a proper "auto power off = never" command to the MCU over `ttyATH0`, and confirming
the exact idle timeout (one run cut at 670 s uptime).

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
