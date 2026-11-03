# 05 — Firmware internals (uImage / LZMA / rootfs)

`tools/unpack_firmware.py` automates everything here.

## uImage kernels

Both kernel slots start with a U-Boot legacy image header (magic `27 05 19 56`, big-endian):

- name: `MIPS OpenWrt Linux-3.10.49`
- load address / entry point: `0x80060000`
- compression: LZMA (payload follows the 64-byte header)

## LZMA quirk — non-standard properties byte

The payload is **LZMA "alone" format**, but **not** the usual `5D 00 00 …` you see in most
OpenWrt images. The first bytes are:

```
6D 00 00 80 00 ...
^^ properties = 0x6D  -> lc=1, lp=2, pb=2   (not the default lc=3,lp=0,pb=2 = 0x5D)
   00 00 80 00        -> dictionary size = 0x00800000 = 8 MB
   (then 8-byte uncompressed size, little-endian)
```

A strict `5D 00 00` magic check **fails** here. Decompress by feeding the payload straight to a
decoder that reads the 13-byte LZMA-alone header itself, e.g. in Python:

```python
import lzma
lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(payload)
```

(The A-slot kernel payload decompresses to a ~14 MB `vmlinux`.)

## The rootfs is an embedded cpio initramfs (no squashfs)

There is **no squashfs anywhere in the flash**. The rootfs is a **`newc` cpio initramfs built
into the kernel** (the kernel's `.init.ramfs`). After decompressing the kernel, find the cpio:

- `newc` entries begin with the ASCII magic `070701`.
- **Decoy:** the kernel's own error-string table contains the literal string `070701` followed by
  `"no cpio magic" / "broken padding"` — that is **not** the archive.
- **Find the real one by validation:** for each `070701` offset, try to walk the chain (each entry
  is a 110-byte ASCII header: magic + 13×8 hex fields; then name padded to 4; then data padded to
  4). The real archive is the long chain (hundreds of entries) that ends in a `TRAILER!!!` entry.

On this build the real initramfs started a few hundred KB past the decoy, with ~600 entries.
Offsets are build-specific — use the validation approach, don't hard-code an offset.

## Rootfs contents (OpenWrt Barrier Breaker 14.07)

Standard OpenWrt tree plus DJI bits. Notables:

- **`/sbin/apsrv`** — the main DJI daemon. Relays between app ⇄ RC ⇄ aircraft ⇄ MCU
  (`app2ykq`/`ykq2app`, `pla2ykq`/`ykq2pla`, `push_*_to_{app,pc,mcu}`, `heart_beat`). "ykq" =
  *yáokòngqì* = remote controller. Handles MCU firmware update (`/tmp/fw_mcu.bin`). This is where
  stick/channel handling lives — the target for "broader control" changes.
- **`/usr/sbin/dji_verify`** — signature verification (checks DJI's signed config blobs, e.g.
  `/etc/amt/fwbak/*.cfg.sig`). Expect signature checks somewhere in the update path; verify before
  trusting that a modified image will boot/accept.
- **`/usr/sbin/telnetd`** present, started by `/etc/init.d/telnet` — but the OpenWrt start gate
  only launches it **if root has no password**. Since root *has* a password, telnet is off by
  default. Forcing it on (firmware mod) gives a **root shell over the softAP** — a much nicer
  channel than serial. (Moot while the AR6006 is down; see `docs/06`.)
- **`lsz`/`lrz`** (ZMODEM), **`vsftpd`** (FTP), **`usbmuxd`** (the AOA/phone link), `wpad`/hostapd.
- Startup: `/etc/init.d/rcS_ykq_wm100` (plus `_factory`, `_phy` variants).
- `/etc/shadow` holds the root hash (the shared DJI password above).

## Modify + repack (outline)

To change the rootfs and reflash a kernel slot:

1. Extract the initramfs (`unpack_firmware.py`), edit files.
2. Re-create the `newc` cpio.
3. LZMA-compress it back **with the same parameters** (alone format, props `0x6d` = lc1/lp2/pb2,
   8 MB dict) as part of the kernel image, or rebuild the whole kernel if you have the source.
4. Wrap in a uImage (name, load/entry `0x80060000`, recompute the header + data CRC32s).
5. Write into **one** kernel slot (`mtd write`), keeping the other as a stock A/B fallback. Mind
   any signature check (`dji_verify`) in the update path.

> Repacking the embedded-initramfs kernel without the kernel source is non-trivial (the cpio is
> inside the compressed kernel image, not a separate partition). This section is an outline;
> the repack/reflash is still being worked out.
