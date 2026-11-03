# 04 — Dumping the 8 MB flash over the serial console

No SPI clip required. The whole chip (`/dev/mtd5`, 8 MB) can be pulled over the 115200 console.
`tools/serial_dump.py` implements everything below.

## Why it needs care

1. **Console flood.** `apsrv` spams the console (~2 lines/s) and you **must not stop it**
   (watchdog reset — see `docs/06`). So the dump stream is interleaved with log lines and must be
   made robust to that, host-side.
2. **No `base64`/`od` in PATH.** This BusyBox build has **no `base64` or `od` symlink**, but the
   **applets exist** — call them as **`busybox base64`**. (Present: `dd`, `md5sum`, `busybox base64`,
   `hexdump`, `gzip`, `tar`, `nc`, `tftp`, and **`lsz`/`lrz` = ZMODEM** — see below.)
3. **Live flash can change mid-dump.** Runtime writes to some regions (e.g. A/B kernel
   housekeeping) mean a single whole-image `md5sum` taken at the end may not match a 30+ min dump.
   Verify **per block** and only re-read the block(s) that differ.

## Method (block + per-block md5 + flood-tolerant parse)

Read the chip in **128 × 64 KB blocks**. For each block `N`, issue on the console:

```sh
dd if=/dev/mtd5 bs=65536 skip=N count=1 2>/dev/null >/tmp/b
md5sum /tmp/b
busybox base64 /tmp/b
```

wrapped in unique start/end markers. Host side:

- Match markers with **`rfind`**, and wait for the marker to appear **twice** (once as the command
  echo, once as real output) — otherwise you parse the echoed command, not the result.
- **Leading-run parser for the flood:** the base64 alphabet contains no `[`, `]`, `:`, `_`, or
  space, and each flood line (`[SW_Pro_Gnd_Manage_Send_Req] …`) ends with its own newline, so
  base64 always resumes on the next line. **Keep only the leading run of base64 characters on each
  line** and concatenate. This reassembles the base64 intact regardless of where a flood line lands.
- Decode, require **exactly 65536 bytes**, and require the decoded block's md5 to equal the
  `md5sum /tmp/b` value the RC reported. **Retry the block** on any mismatch (don't silently accept
  a block whose md5 line was itself corrupted by the flood).

Finally, cross-check the whole image against a fresh `md5sum /dev/mtd5`. If it differs but every
block verified, re-read only the mismatching partition's blocks while the flash is idle/stable,
then re-check.

Throughput at 115200 is ~11 KB/s of base64, so ~30–35 min for 8 MB including flood retries
(~40–50 % of blocks need at least one retry). Make the dump **resumable** (track completed blocks
in a state file) so a sleep/disconnect doesn't cost you the whole run.

## Faster/alternative: ZMODEM

`lsz` (send) and `lrz` (receive) are on the RC. `lsz -b /dev/mtd5` over the console with a
ZMODEM receiver on the host is more efficient and self-checksumming than base64 — a good upgrade
if your terminal supports it. (The base64 method above was used because it needs nothing beyond
a raw serial reader.)

## Alternative: network (softAP)

If the AR6006 softAP is up (`wlan1`, `192.168.1.1`), join it and
`dd if=/dev/mtd5 | nc <host> <port>` for a fast clean transfer. On this unit the AR6006
enumeration was flaky when partially reassembled / on low battery (`error -32`), so serial was
the dependable path. See `docs/06`.

## Tool

```sh
python tools/serial_dump.py --port COM7 --dev /dev/mtd5 --out dump.bin
# resumable; re-run with the same --out to finish an interrupted dump
```
