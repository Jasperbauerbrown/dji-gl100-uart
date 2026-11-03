# 01 — Hardware

DJI Spark Remote Controller mainboard. DJI internal name **GL100A / "GL100 Main board"**.
PCB part number silkscreen: `P02357.T7`. (The Spark aircraft itself is WM100.)

See the repo [`README`](../README.md) for the UART pad pinout and board photos.

## Main components

| Function | Part | Notes |
|----------|------|-------|
| SoC / WiSoC | **Qualcomm Atheros AR9342-BL1A** | MIPS 74Kc @ 500 MHz, ath79/ar71xx, OpenWrt-class. Boots from external SPI NOR via U-Boot. Host-only USB (EHCI). |
| DRAM | **Winbond W9751G6KB-25** | 512 Mbit DDR2 = 64 MB |
| SPI NOR flash | **Winbond W25Q64 (J/F)V** SOIC-8, 208-mil (wide) | 8 MB, 3.3 V. Linux/flashrom ID `s25fl064k` / `W25Q64.V`. |
| softAP Wi-Fi | **QCA6006X-AL3A** | A USB-attached radio → Linux `ath6kl_usb` / AR6006. Hosts the `Spark-RC-xxxxxx` softAP (`wlan1`). |
| Aircraft-link Wi-Fi | AR9342 built-in MAC/PHY | `ath9k` + **`ath9k_5m`** (5 MHz narrowband "Enhanced Wi-Fi"), `wlan0`, IBSS mode. |
| Stick/button MCU | **STMicro STM32F051K8** | Cortex-M0. Reads the control sticks, handles buttons, and **owns the idle auto-power-off** timer. Firmware updated from Linux as `fw_mcu.bin`. **No USB peripheral on the F051.** |
| Stick position sensors | **Melexis MLX90393** (x2) | 3-axis Hall sensors under the gimbals. |
| Battery charger | **TI BQ24259** | On the micro-USB (charge in). |
| USB hub | **Genesys GL850** | Behind the micro-USB / internal USB bus; the AR6006 sits on a hub port. |
| RF PA | **Skyworks SKY85809** | |
| Antennas | 2× U.FL | |

## USB port is host-only (not a PC data channel)

The micro-USB port is a **USB host/OTG-host** port. DJI drives the phone via **AOA (Android
Open Accessory)** — in AOA the *accessory* (the RC) is the USB **host** and the phone is the
**device**. The port also carries charge-in (BQ24259).

The AR9342 has **only a host EHCI controller — no USB device/gadget (UDC) IP** — and you can't
flip a host controller into device mode; it is different silicon. No other chip on the board
can present a general USB-device interface to a PC (GL850 is a hub; AR6006 is a fixed-function
USB device on the *internal* bus; the STM32F051 has no USB at all).

**Consequence:** the RC will **never enumerate as a USB device to a PC**, by any
firmware/software change. PC-facing channels are: **UART serial** (this repo), the **softAP
Wi-Fi**, and an **SPI flash clip**. Plugging the RC into a PC with a data cable yields nothing
(no COM port, no PnP device) — two USB hosts facing each other.

## Reference

The [dji-firmware-tools GL100 wiki page](https://github.com/o-gs/dji-firmware-tools/wiki/GL100-Main-board)
confirms the chip list. Sister module for cross-reference: the AR9342-based DJI "m0700".
