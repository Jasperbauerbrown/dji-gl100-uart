# 03 — Flash layout (MTD map)

8 MB SPI NOR (Winbond W25Q64), one MTD device (`ath-nor0`), 64 KB erase blocks.
From `cat /proc/mtd`:

| dev  | name        | start     | end       | size      | notes |
|------|-------------|-----------|-----------|-----------|-------|
| mtd0 | `u-boot`    | 0x000000  | 0x040000  | 0x040000  | bootloader |
| mtd1 | `u-boot-env`| 0x040000  | 0x050000  | 0x010000  | U-Boot environment |
| mtd2 | `kernel1`   | 0x050000  | 0x450000  | 0x400000  | **A-slot** uImage (kernel + embedded rootfs) |
| mtd3 | `kernel2`   | 0x450000  | 0x770000  | 0x320000  | **B-slot** uImage |
| mtd4 | `firmware1` | 0x050000  | 0x770000  | 0x720000  | overlaps kernel1+kernel2 (whole firmware region) |
| mtd5 | `all`       | 0x000000  | 0x800000  | 0x800000  | the entire chip — **dump this** |
| mtd6 | `art`       | 0x7f0000  | 0x800000  | 0x010000  | Atheros radio calibration — **DO NOT ERASE** |
| mtd7 | `amt`       | 0x770000  | 0x7f0000  | 0x080000  | DJI area: per-unit cal / serial / pairing |

Notes:
- **Dual-kernel A/B.** Both `kernel1` and `kernel2` are standalone `uImage`s that boot
  independently (same load/entry `0x80060000`). Keep one slot stock as a recovery fallback when
  experimenting on the other.
- **`firmware1`** is just a window over both kernel slots; it is not a separate filesystem.
- **There is no separate rootfs/squashfs partition** — the rootfs is an initramfs embedded
  *inside* each kernel image. See `docs/05-firmware-internals.md`.
- **`art` (mtd6)** holds radio calibration — never write it. **`amt` (mtd7)** holds per-unit
  data (serial, pairing, cal); treat its contents as personal and do not publish a raw dump of it.
- Full-chip `md5sum /dev/mtd5` is **per-unit** (because `art`/`amt` differ) — your hash will not
  match anyone else's. The `u-boot`, `kernel*`, and `firmware1` regions should match across units
  on the same firmware version.

## Dumping

See [`docs/04-dumping-over-serial.md`](04-dumping-over-serial.md). Dump `mtd5` (whole chip) so
you have u-boot, both kernels, art and amt in one verified image.
