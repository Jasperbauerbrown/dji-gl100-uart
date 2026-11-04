# 00 — Overview & status

Companion documentation to the repo [`README.md`](../README.md). The README documents the
**UART pad locations** (exact SoC pins, pixel coordinates, photos). These docs continue from
there: they confirm the console **accepts input**, that the **U-Boot serial abort is disabled**,
how to get a **root shell**, how to **dump the 8 MB flash over the console**, and what's inside
the firmware image — i.e. the items the README listed as "not yet verified."

> **Scope / intent:** right-to-repair and hobbyist research on **hardware you own**. The root
> password used here is DJI's *shared firmware* password (identical across many DJI products and
> long known in the RE community), not a per-unit secret.

## Status

| Item | State |
|------|-------|
| UART pads located (pins, coords, photos) | ✅ see [`README`](../README.md) |
| Console baud / level | ✅ 115200 8N1, 3.3 V, `ttyS0` |
| Console accepts input (RX works) | ✅ (README had this "to be documented") |
| U-Boot serial autoboot-abort | ❌ disabled by DJI (`Press S` is vestigial) |
| Root shell via console login | ✅ `root` / shared DJI firmware password |
| Full 8 MB SPI flash dumped & verified | ✅ over the serial console (no SPI clip needed) |
| Firmware image structure decoded | ✅ A/B uImage, LZMA kernel, embedded cpio rootfs |
| Rootfs extracted | ✅ OpenWrt Barrier Breaker 14.07, kernel 3.10.49 |
| Modify + reflash | ⏳ in progress ([`05`](05-firmware-internals.md)) |

## Documents

- [`01-hardware.md`](01-hardware.md) — chips & roles, and why the USB port can't be a PC data channel.
- [`02-uart-console.md`](02-uart-console.md) — baud, how TX/RX were found, autoboot-abort disabled, **root login**.
- [`03-flash-layout.md`](03-flash-layout.md) — MTD partition map, A/B kernels.
- [`04-dumping-over-serial.md`](04-dumping-over-serial.md) — dumping 8 MB over a 115200 console, reliably.
- [`05-firmware-internals.md`](05-firmware-internals.md) — uImage/LZMA quirks, embedded initramfs, rootfs contents.
- [`06-gotchas-and-findings.md`](06-gotchas-and-findings.md) — watchdog, USB-wifi enumeration, auto power-off, telnet gate.
- [`07-network-protocol-and-crypto.md`](07-network-protocol-and-crypto.md) — TCP 19003/19005 SW_Alg framing, DUML XOR key table, video path, signature-check reality.
- [`../tools/`](../tools/) — `serial_dump.py`, `unpack_firmware.py`, `rc_keepalive.sh`.

## Quick start

1. Connect a **3.3 V** USB-serial adapter to the UART pads (see [`README`](../README.md) for exact pads; GND/TX/RX).
2. `python tools/serial_dump.py --port COM7 --dev /dev/mtd5 --out dump.bin` — logs in, dumps, verifies.
3. `python tools/unpack_firmware.py dump.bin out/` — decompresses the kernels, extracts the rootfs.

## Firmware

OpenWrt **Barrier Breaker 14.07** (r5401, ar71xx/generic), kernel **3.10.49**, DJI firmware
**v3.1.49**, BusyBox, IPv6 disabled.
