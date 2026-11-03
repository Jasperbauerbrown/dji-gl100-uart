#!/usr/bin/env python3
"""
serial_dump.py - dump an MTD partition from a DJI GL100 (Spark RC) over its 115200
serial console, flood-tolerant and md5-verified per block. Resumable.

Needs only pyserial on the host. On the RC it uses `dd`, `md5sum`, and the BusyBox
`base64` applet (called as `busybox base64`, since there is no `base64` symlink in PATH).

The DJI app daemon `apsrv` floods the console with log lines. We do NOT stop it (that
trips a watchdog -> reset); instead we parse around the flood: the base64 alphabet has
no '[', ']', ':', '_' or space, and each flood line ends with its own newline, so we
keep only the leading run of base64 chars on each line and concatenate.

Example:
    python serial_dump.py --port COM7 --dev /dev/mtd5 --out dump.bin
    # resumable: re-run with the same --out to finish an interrupted dump

See docs/04-dumping-over-serial.md for the full rationale.
"""
import argparse, serial, time, re, base64, hashlib, os, json, sys

B64SET = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
MD5LINE = re.compile(rb'([0-9a-f]{32})\s+/tmp/b')


def clean_b64(seg):
    """Keep only the leading base64-char run of each line (strips interleaved console flood)."""
    out = bytearray()
    for line in seg.split(b'\n'):
        line = line.rstrip(b'\r')
        if b'/tmp/b' in line:          # the md5sum line (its hex is base64-ish) - skip
            continue
        k = 0
        while k < len(line) and line[k] in B64SET:
            k += 1
        out += line[:k]
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description="Dump an MTD partition over the RC serial console.")
    ap.add_argument("--port", default="COM7", help="serial port (default COM7)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--dev", default="/dev/mtd5", help="device to dump (default /dev/mtd5 = whole chip)")
    ap.add_argument("--out", default="dump.bin", help="output file (resumable)")
    ap.add_argument("--size", type=lambda x: int(x, 0), default=0x800000, help="total size in bytes (default 8MB)")
    ap.add_argument("--bs", type=lambda x: int(x, 0), default=0x10000, help="block size (default 64KB)")
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default="Big~9China", help="shared DJI firmware root password")
    ap.add_argument("--retries", type=int, default=12)
    args = ap.parse_args()

    BS = args.bs
    NBLK = args.size // BS
    assert args.size % BS == 0, "size must be a multiple of bs"
    state_path = args.out + ".state.json"

    s = serial.Serial(args.port, args.baud, timeout=0.1)

    def drain(t):
        e = time.time() + t; b = b""
        while time.time() < e:
            b += s.read(16384)
        return b

    def w(x):
        s.write(x if isinstance(x, bytes) else x.encode()); s.flush()

    # output file + resume state
    if not os.path.exists(args.out) or os.path.getsize(args.out) != args.size:
        with open(args.out, "wb") as f:
            f.truncate(args.size)
    done = set()
    if os.path.exists(state_path):
        try:
            done = set(json.load(open(state_path)))
        except Exception:
            done = set()

    # log in (break any line-continuation first), quiet kernel log only
    s.reset_input_buffer()
    w(b"\x03"); drain(0.4); w("\r"); o = drain(1.0)
    if b"login" in o.lower() or b"password" in o.lower():
        w(args.user + "\r"); drain(1.0); w(args.password + "\r"); time.sleep(1.8); drain(0.4)
    w("echo 0 >/proc/sys/kernel/printk\r"); drain(0.5)

    def fetch_block(n):
        S = f"BLKSTART{n}Z".encode(); E = f"ZBLKEND{n}".encode()
        s.reset_input_buffer()
        cmd = (f"echo BLKSTART{n}Z; dd if={args.dev} bs={BS} skip={n} count=1 2>/dev/null >/tmp/b;"
               f" md5sum /tmp/b; busybox base64 /tmp/b; echo ZBLKEND{n}\r")
        w(cmd)
        buf = b""; deadline = time.time() + 25
        while time.time() < deadline:
            buf += s.read(16384)
            if buf.count(E) >= 2:       # 1st = command echo, 2nd = executed output
                break
        i = buf.rfind(S); j = buf.rfind(E)
        if i == -1 or j == -1 or j < i:
            return None
        seg = buf[i + len(S):j]
        mm = MD5LINE.search(seg); exp = mm.group(1).decode() if mm else None
        try:
            data = base64.b64decode(clean_b64(seg))
        except Exception:
            return None
        if len(data) != BS:
            return None
        if not exp:                      # md5 line unreadable -> retry (no silent accept)
            return None
        if hashlib.md5(data).hexdigest() != exp:
            return None
        return data

    f = open(args.out, "r+b")
    t0 = time.time()
    for n in range(NBLK):
        if n in done:
            continue
        data = None
        for attempt in range(args.retries):
            data = fetch_block(n)
            if data is not None:
                break
        if data is None:
            print(f"block {n} FAILED after {args.retries} retries; stopping (re-run to resume)")
            break
        f.seek(n * BS); f.write(data); f.flush()
        done.add(n); json.dump(sorted(done), open(state_path, "w"))
        if n % 8 == 0 or n == NBLK - 1:
            print(f"block {n} ok | {len(done)}/{NBLK} ({len(done)*100//NBLK}%) | {time.time()-t0:.0f}s")
    f.close()

    if len(done) == NBLK:
        h = hashlib.md5(open(args.out, "rb").read()).hexdigest()
        print(f"ALL BLOCKS DONE. local md5={h}")
        # whole-image cross-check (may differ if the live flash changed during the dump)
        s.reset_input_buffer()
        w(f"echo MD5START; md5sum {args.dev}; echo MD5END\r")
        buf = b""; dl = time.time() + 40
        while time.time() < dl:
            buf += s.read(16384)
            if buf.count(b"MD5END") >= 2:
                break
        mm = re.search(rb'([0-9a-f]{32})\s+' + re.escape(args.dev.encode()), buf)
        rc = mm.group(1).decode() if mm else "??"
        print(f"RC md5={rc} -> {'MATCH' if rc == h else 'MISMATCH (re-read changed region while idle)'}")
    else:
        print(f"INCOMPLETE: {len(done)}/{NBLK} blocks. Re-run with the same --out to resume.")
    s.close()


if __name__ == "__main__":
    sys.exit(main())
