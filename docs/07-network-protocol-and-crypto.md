# 07 — Network protocol & crypto (apsrv / libcommon)

Findings from static reverse-engineering of `apsrv` (229 kB, MIPS32 BE, stripped) and
`libcommon.so`, all from the extracted rootfs — no device interaction. Offsets are
file offsets in the respective binary unless marked as virtual addresses (`va`).
Toolchain used: capstone MIPS32 big-endian, `$gp` = 0xa22b0 for `libcommon.so`.

## TCP surface

| Port | Role | Entry |
|---|---|---|
| 19005 | command channel (GndEntry) | `My_Tcp_Agent_Entry_Init(GndEntry, 1, 0, 19005)` at apsrv `0x1e040` |
| 19003 | telemetry push (UavEntry) | `My_Tcp_Agent_Entry_Init(UavEntry, 1, 0, 19003)` right after it |

Both run the same `My_Tcp_Agent` code in `libcommon.so`, so framing is identical on
both. PLT stubs resolve via `.rel.plt` → GOT (`0x442e64` =
`My_Tcp_Agent_Entry_Init`, `0x442db8` = `My_Tcp_Agent_Start`).

## There is no handshake magic

The RC does not expect any fixed hello bytes. What a client must send is a valid
**SW_Alg stream frame** from the first byte.

- The "ios device first recv" hook (`libcommon.so` 0x12d00 region) is **log + flag
  only**: it calls `recv_cb(arg, buf, 0x400)`, logs `"ios device first recv,
  type:%d, port:%d"`, and sets a flag byte at entry+0x24. **No byte comparison
  anywhere in the path.**
- `My_Tcp_Server_Run` = 0x14674 is a plain accept loop (listen setup 0x14abc,
  backlog 0x80; `My_Tcp_Peer_Add` = 0x143e4; 0x1452c = `My_Tcp_Peer_Stop`). No data
  exchange at accept time.
- `SW_Alg_Recv_Init` (0x1c428) only allocates — no magic constants.

If a connection "resets on any data", that is the parser discarding/resyncing on
bytes that don't parse as a frame — not a handshake rejection.

## SW_Alg frame format (parser at 0x289fc)

```
len       = ((buf[0] & 0x3f) << 8) | buf[1]     # 14-bit frame length, 2 flag bits
frame_end = buf + len
p         = buf + 8                             # 8-byte frame header

record 1: 4-byte LE field at p -> SW_Alg_Recv_Deal_Win(ctx->0x38, p+2, p); p += 8
record 2: 4-byte LE field at p -> SW_Alg_Recv_Deal_Win(ctx->0x4c, p+2, p); p += 8
record 3: 4-byte LE field at p -> SW_Pro_Deal_Send_Ack(...);            p += ret + 4
record 4: 2-byte LE len at p   -> payload dispatched to ctx->8->0x40    (DUML handler)
```

- `SW_Alg_Recv_Deal_Win` (0x1f38c, assert string names it
  `SW_Alg_Recv_Stream_Deal_Data`) does sliding-window sequence accounting via
  `SW_SeqNum_IsInLeftGap` — window/seq bookkeeping, not magic matching.
- `SW_Pro_Deal_Send_Ack` (0x2565c) handles ACK records.
- The RC **sends first** after a client connects (window sync / ACK records). The
  byte-exact template of that first frame is best recovered with a short live
  capture on the RC (`tcpdump -i br-lan port 19005 -s0 -w /tmp/cap.pcap` while the
  DJI app connects) rather than by finishing the send-side walkthrough
  (`SW_Alg_Send_Send_Data` / `SW_Alg_Send_Get_Send_Pkt`, ~0x18968 region; the label
  table there is unreliable).

## Video path — plaintext H.264, over WiFi

- `apsrv` relays the aircraft's H.264 stream in **userspace, in plaintext**. There
  is **no crypto on the video path**: XOR (below) is DUML control only, and
  AES-128-CBC (`AesEncrypt`, lc:0x9f24) is reachable only from
  `AesEncryptToFile`/`AesDecryptFromFile` (file/upgrade use). apsrv's own AES
  tables are dead code.
- The UDP 10002 video channel rides **wlan0/ath9k OFDM**, not the `h2h` link:
  `h2h.ko` is embedded in the kernel image (ELF at vmlinux offset 0x560da6, string
  `"usb h2h module init ok"`) and is the **USB** link.
- A PC-side video client therefore needs: connect to the RC WiFi, open TCP to
  19005/19003, speak SW_Alg framing, resync on any Annex-B start code, feed an
  H.264 decoder. Video-only clients likely need no encryption.

## DUML payload XOR — key table recovered

`Simple_EncryptAndDecrypt` (`libcommon.so` 0xa6fc), signature
`(uint8 *buf, int len, uint16 key16)`, applies to the **control path only**.
Gated by `Pro_IsPacketNeedEncrypt` (lc:0xaf28), which exempts type-2 cmds
0x10/0x11/0x70/0x71.

- Table pointer variable at data va `0x97040` (file offset `0x87040`, big-endian
  word) = `0x83d5c` (rodata); table length variable at va `0x97030` = 0x15 (21).
- **Key table (21 bytes) at rodata 0x83d5c:**

```
78 4f 24 33 28 2d 32 40 23 6c 64 2a 76 69 41 51 7e 69 78 46 45
```

- Algorithm (from the 0xa6fc disassembly):

```c
idx = 0;
for (i = 0; i < len; i++) {
    idx = (idx + 1) ^ (i & 0xf);
    if (idx > 21) idx = 0;              // sltu wrap
    buf[i] ^= table[idx];
    buf[i] ^= (i & 1) ? (key16 >> 8) & 0xff : key16 & 0xff;
}
```

Self-inverse (XOR both ways). `Pro_Init` (lc:0xc080) is **not** the initializer —
it is plain struct init (memset, DataBuff_Create, DJI_ProStruct_Init, mutex) with
no table writes.

## apsrv command dispatch — callback-based

Dispatch goes through `Pro_Deal_CallBack` (lc:0xae90) → `pkt->0x60`. A full-file
function-pointer-run scan found only the transport-ops table @0x42d400, a
selfcheck table @0x42ea40 and the video tables — **no static
{cmd_set, cmd_id, handler} table exists**. Enumerating the 19005 command surface
means walking the per-handler registrations, not reading a table.

## What is *not* checked

- **No boot-time signature check.** The boot chain never calls `dji_verify`;
  `mount_root` mounts the rootfs without hash checking; no dm-verity in the module
  list. Kernel/rootfs images are plain (uImage CRC32 only, recomputed by repack
  tools). Self-built images with a correct uImage CRC boot.
- `dji_verify` (53 kB) authenticates **upgrade packages** only, with a
  DES/3DES-CBC argv shape (`in && out && key`, `... && ivec`; strings
  `invalid auth key: 0x%08x`, `failed: payload digest is not consistent`). apsrv
  calls it as `dji_verify -n %02d%02d -o /tmp/fwtmp %s`. Bypassing it is only
  needed to make the RC accept *DJI-signed* packages — `mtd write` from a shell
  bypasses it entirely.
- The AT88 crypto-auth chip (`at88.ko`, `At88_*` API in libcommon) validates
  factory/calibration state at boot — a hardware gate for cloned boards, but it
  does not block rootfs/kernel mods on a stock unit.

## Do-not-touch

Never overwrite the `amt` (0x780000, jffs2 config/calibration — MCU writes there
are MD5-block-protected) or `art` (0x7F0000, radio calibration) partitions.
Losing `art` kills WiFi; losing `amt` can trip the At88 checks at boot. Always
back up the full 8 MB before writing anything. U-Boot serial (`bootm 0x9f050000`
/ `0x9f450000`, two slots) is the recovery path.

## Still open

- Byte-exact first SW_Alg frame (record field semantics: seq numbers, ack bitmap)
  — live capture settles it.
- Full 19005 command surface (per-handler walkthrough).
- Where `dji_verify`'s key/ivec argv values originate (apsrv upgrade path;
  `strace`/`ps` during a live upgrade would show them).
