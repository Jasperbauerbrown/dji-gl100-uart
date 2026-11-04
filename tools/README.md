# Tools

Pure-Python, stdlib-only except `serial_dump.py` which needs `pyserial`.

## `serial_dump.py`
Dump an MTD partition from the RC over its 115200 serial console. Flood-tolerant,
md5-verified per block, resumable. See [`../docs/04-dumping-over-serial.md`](../docs/04-dumping-over-serial.md).

```sh
pip install pyserial
python serial_dump.py --port COM7 --dev /dev/mtd5 --out dump.bin
```

Options: `--port --baud --dev --out --size --bs --user --password --retries`.
Re-run with the same `--out` to resume an interrupted dump.

## `unpack_firmware.py`
Decode a dump: parse the uImage headers, LZMA-decompress the kernels (handles the
non-standard props byte `0x6d`), locate the embedded `newc` cpio initramfs by chain
validation, and extract the rootfs. See [`../docs/05-firmware-internals.md`](../docs/05-firmware-internals.md).

```sh
python unpack_firmware.py dump.bin out/
```

Output: `out/kernelN_vmlinux.bin` and `out/rootfsN/` (+ `_manifest.txt`).

> Your dump and anything extracted from it contain **per-unit** data (serial, pairing, radio
> calibration in the `amt`/`art` regions, and possibly Wi-Fi keys in the rootfs). **Do not commit
> dumps or extracted trees** — `.gitignore` excludes them.

## `rc_keepalive.sh`
Runs **on the RC**. Stops the MCU auto power-off by injecting a small stick blip into
`/dev/input/event0` every 30 s. Copy it to `/tmp` (paste it over the console) and start it with
`sh /tmp/rc_keepalive.sh &`. It is RAM only, so start it again after each boot. ⚠️ It is real
stick input: don't run it with an aircraft linked. See [`../docs/06-gotchas-and-findings.md`](../docs/06-gotchas-and-findings.md).
