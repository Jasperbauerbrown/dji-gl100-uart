# 02 — UART console & root shell

> The repo [`README`](../README.md) gives the **exact pad locations** (SoC pins TX=GPIO10/B46,
> RX=GPIO9/A53, coordinates, and photos). This page is the **method** used to find them and —
> newly — what the console does once you're connected: it **accepts input**, the **U-Boot abort
> is disabled**, and you can get a **root shell**.

## Parameters

- **Signal level: 3.3 V** (do not use a 5 V adapter).
- **115200 8N1**, Linux console on `ttyS0`.
- A second UART `ttyATH0` exists (base `0x18500000`) but is **not** the console.

The AR9342 default console is `ttyS0,115200`; the readable U-Boot/Linux boot log confirms
115200. There is **no baud sweep needed** — at the real TX pad, 115200 gives clean ASCII;
anything else is not the TX pad.

## Finding the pads

The service pads are small, near the AR9342, and were undocumented. Method that worked:

1. **GND** — a large gold/tinned rectangle pad; confirm with a meter against chassis/USB-shield ground.
2. **TX (board → adapter)** — the real TX **idles HIGH** and shows **data flicker**. On an
   FT232RL the **RX LED flickers** when you touch the real TX at power-on. Candidate pads that
   **idle LOW** are coupling/noise, not TX. Use a **wide capture window (≥ 25 s)** and a single
   power-cycle; boot bursts are easy to miss with short windows.
3. **RX (adapter → board)** — the **echo-sweep** method is far more reliable than guessing:
   boot to the `dji login:` prompt, then **stream a single character** (e.g. `Z`) from the
   adapter TX while sweeping it across candidate pads. The getty **echoes** the character back
   on your TX line **only when you touch the real RX**. (This found RX after ~6 blind guesses failed.)

Solder solid taps to TX and RX — hand-held probes drop contact constantly (a floating TX once
produced ~10 MB of garbage). A solid joint gives a clean log.

> Earlier noise/coupling captures soft-decoded to "19200" — that was an **artifact**; the real
> baud is 115200. Wrong-baud garbage tends to show as `0x80/0xC0/0xE0/0xF8` bytes with `0x00` runs.

## U-Boot: serial autoboot-abort is DISABLED

The boot banner says `Press S to abort autoboot in 1s`, but **DJI removed the serial key-check**.
Streaming `S` (or any key) densely on a confirmed-good RX across multiple boots **never** aborts
— it always boots through to Linux. **U-Boot-over-serial is a dead end on this board.** Get root
via the Linux login instead (below), or use an SPI clip if you need pre-boot access.

Boot chain summary (from the log): U-Boot → LZMA uImage kernel, load/entry `0x80060000`,
64 MB DRAM → OpenWrt/Linux.

## Root shell via console login

After boot the console reaches `dji login:` and then floods with application logs
(`[SW_Pro_Gnd_Manage_Send_Req]` every ~0.5 s, plus MLX90393 sensor-reset kernel messages).

- **User:** `root`
- **Password:** DJI's **shared firmware root password** (the well-known `Big~9China`, identical
  across many DJI products — *not* a per-unit secret). `uid=0`.

To verify you really have a shell despite the log flood, run a command whose output you can
distinguish from the echo, e.g. `echo RZ_$((6*7))_ZR` → a real shell prints `RZ_42_ZR`.

### Quieting the console

- Kernel messages: `echo 0 > /proc/sys/kernel/printk`.
- The app log flood comes from the `apsrv` daemon. **Do NOT `kill -STOP apsrv`** — see
  `docs/06-gotchas-and-findings.md` (it trips a watchdog → reset). For bulk transfers, tolerate
  the flood and filter it on the host side (see `docs/04`).

## System

OpenWrt **Barrier Breaker 14.07** (r5401, ar71xx/generic), kernel **3.10.49**
(`#185 Jul 13 2018`), hostname `dji`, BusyBox, IPv6 disabled. DJI firmware version **v3.1.49**.
