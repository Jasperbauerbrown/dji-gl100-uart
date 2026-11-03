#!/usr/bin/env python3
"""
unpack_firmware.py - decode a DJI GL100 (Spark RC) flash dump.

Given a full 8MB dump (or just a kernel slot), this:
  1. parses the U-Boot uImage header(s) at the kernel partitions,
  2. LZMA-decompresses the kernel payload (handles the non-standard props byte 0x6d),
  3. locates the embedded `newc` cpio initramfs by chain-validation (ignoring the kernel's
     `070701` error-string decoy),
  4. extracts the rootfs.

Pure stdlib. Usage:
    python unpack_firmware.py dump.bin out/
    python unpack_firmware.py dump.bin out/ --slots 0x50000 0x450000

See docs/05-firmware-internals.md.
"""
import argparse, struct, lzma, gzip, os, sys, stat

UIMAGE_MAGIC = b"\x27\x05\x19\x56"


def decompress(payload):
    """Decompress a kernel payload. Handles LZMA-alone with any props byte, plus gzip/xz."""
    if payload[:2] == b"\x1f\x8b":
        return gzip.decompress(payload)
    if payload[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(payload)
    # LZMA-alone (OpenWrt), ANY properties byte. On GL100 props=0x6d (lc1/lp2/pb2), 8MB dict.
    d = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    return d.decompress(payload)


def parse_uimage(dump, off):
    hdr = dump[off:off + 64]
    if hdr[:4] != UIMAGE_MAGIC:
        return None
    size = struct.unpack(">I", hdr[12:16])[0]
    load = struct.unpack(">I", hdr[16:20])[0]
    ep = struct.unpack(">I", hdr[20:24])[0]
    name = hdr[32:64].split(b"\x00")[0].decode("latin1", "replace")
    return {"name": name, "size": size, "load": load, "entry": ep,
            "payload": dump[off + 64: off + 64 + size]}


def align4(x):
    return (x + 3) & ~3


def cpio_chain_len(blob, start, limit=8000):
    """Validate a newc cpio chain at `start`; return (entries, ends_in_trailer)."""
    p = start; n = 0
    while n < limit:
        if blob[p:p + 6] != b"070701":
            return n, False
        try:
            fld = [int(blob[p + 6 + i * 8:p + 6 + i * 8 + 8], 16) for i in range(13)]
        except ValueError:
            return n, False
        nsize = fld[11]; fsize = fld[6]
        if nsize > 4096 or fsize > 100_000_000:
            return n, False
        name = blob[p + 110:p + 110 + nsize - 1]
        he = align4(p + 110 + nsize); nxt = align4(he + fsize)
        if name == b"TRAILER!!!":
            return n, True
        n += 1; p = nxt
    return n, False


def find_initramfs(vmlinux):
    """Return the offset of the real embedded cpio (longest valid chain ending in TRAILER)."""
    best = None; pos = vmlinux.find(b"070701")
    while pos != -1:
        n, trailer = cpio_chain_len(vmlinux, pos)
        if trailer and n >= 10 and (best is None or n > best[0]):
            best = (n, pos)
        pos = vmlinux.find(b"070701", pos + 1)
    return best  # (entries, offset) or None


def extract_cpio(blob, start, outdir):
    os.makedirs(outdir, exist_ok=True)
    man = open(os.path.join(outdir, "_manifest.txt"), "w", encoding="utf-8")
    p = start; reg = dirs = lnk = dev = 0
    while True:
        if blob[p:p + 6] != b"070701":
            break
        fld = [int(blob[p + 6 + i * 8:p + 6 + i * 8 + 8], 16) for i in range(13)]
        mode = fld[1]; fsize = fld[6]; nsize = fld[11]
        name = blob[p + 110:p + 110 + nsize - 1].decode("latin1")
        he = align4(p + 110 + nsize); data = blob[he:he + fsize]; nxt = align4(he + fsize)
        if name == "TRAILER!!!":
            break
        safe = name.lstrip("/").replace("..", "__")
        full = os.path.join(outdir, *safe.split("/")) if safe else None
        ft = stat.S_IFMT(mode)
        if ft == stat.S_IFDIR:
            dirs += 1
            if full:
                os.makedirs(full, exist_ok=True)
        elif ft == stat.S_IFREG:
            reg += 1
            if full:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                open(full, "wb").write(data)
            man.write(f"F {mode & 0o7777:04o} {fsize:>9} {name}\n")
        elif ft == stat.S_IFLNK:
            lnk += 1
            man.write(f"L {name} -> {data.decode('latin1')}\n")
        else:
            dev += 1
            man.write(f"D {oct(mode)} {name}\n")
        p = nxt
    man.write(f"\n# {reg} files, {dirs} dirs, {lnk} symlinks, {dev} special\n")
    man.close()
    return reg, dirs, lnk, dev


def main():
    ap = argparse.ArgumentParser(description="Decode a GL100 flash dump.")
    ap.add_argument("dump")
    ap.add_argument("outdir")
    ap.add_argument("--slots", nargs="*", type=lambda x: int(x, 0), default=[0x50000, 0x450000],
                    help="kernel slot offsets (default 0x50000 0x450000)")
    args = ap.parse_args()

    dump = open(args.dump, "rb").read()
    os.makedirs(args.outdir, exist_ok=True)

    for idx, off in enumerate(args.slots, 1):
        u = parse_uimage(dump, off)
        tag = f"kernel{idx}@0x{off:x}"
        if not u:
            print(f"{tag}: no uImage header"); continue
        print(f"{tag}: '{u['name']}' payload={u['size']} load=0x{u['load']:08x}")
        try:
            vm = decompress(u["payload"])
        except Exception as e:
            print(f"  decompress failed: {e}"); continue
        vmpath = os.path.join(args.outdir, f"kernel{idx}_vmlinux.bin")
        open(vmpath, "wb").write(vm)
        print(f"  vmlinux: {len(vm)} bytes -> {vmpath}")
        found = find_initramfs(vm)
        if not found:
            print("  no embedded cpio initramfs found"); continue
        n, cpio_off = found
        rootfs_dir = os.path.join(args.outdir, f"rootfs{idx}")
        print(f"  initramfs: {n} entries at vmlinux offset 0x{cpio_off:x} -> {rootfs_dir}")
        reg, dirs, lnk, devn = extract_cpio(vm, cpio_off, rootfs_dir)
        print(f"  extracted: {reg} files, {dirs} dirs, {lnk} symlinks, {devn} special")


if __name__ == "__main__":
    sys.exit(main())
