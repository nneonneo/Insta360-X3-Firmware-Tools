## Insta360 X3 Firmware Tools

This repository hosts tools to unpack and repack the firmware for the Insta360 X3. The format is quite similar to the Insta360 Go firmware format, and [@enekochan's Insta360 Go tool](https://github.com/enekochan/insta360-go-firmware-tool) was very useful in figuring out the format.

The main usage of the tool is `fwtool.py [unpack|pack] <firmware.bin> <output directory>`. Using `unpack` will unpack the firmware file into a directory, while `pack` will pack the directory back into a new firmware file suitable for loading onto the device.

The directory format is as follows:

- `metadata.json`: contains miscellaneous information from the firmware file. Most of it should not be edited.
- `f0.bin`: this file is a raw ARM binary containing the ThreadX RTOS that runs on the ARM Cortex-A53 processor. It is loaded at address 0x20000.
- `f1.bin`, `f2.bin`: these two files form the ROM filesystem that is loaded into the RTOS. You can unpack and repack these using `fwtool.py [unpack-romfs|pack-romfs] <fN.bin> <output directory>`.
- `f3.bin`: this is a compressed Linux kernel for the ARM64 application processor.
- `f4.bin`: this is the SquashFS root filesystem for the ARM64 application processor. You can unpack and modify it by using `sudo mount_squashfs.sh f4.bin <mountpoint>`: after mounting, make any changes you want to the mounted filesystem, then run the printed `mksquashfs` command to convert it back into a SquashFS image.
- `f5.bin`: this is the device tree supplied to the Linux kernel. You can modify it by using the `dtc` command: `dtc -I dtb -O dts < f5.bin > f5.dts` to convert it into a text file, and `dtc -I dts -O dtb < f5.dts > f5.bin` to convert it back into a binary file.

## Installing Firmware

After some experimentation, I found an installation strategy that was both easy and fast. However, note that this has only been tested with a single device; use at your own risk!

- Remove the SD card and connect it directly to your computer using an SD card reader. If you do not have an SD card reader, you will have to use the usual update mode.
- Place the firmware file at the root of the SD card, named exactly `Insta360X3FW.bin`.
- Eject the SD card from your computer and set it aside.
- Plug in the camera and turn it on.
- Set the USB mode to "Android", *not* U Disk Mode.
- With the device connected to USB and powered on, remove the battery and insert the SD card.
- The device should immediately begin loading the firmware. Once it finishes and reboots, unplug the USB cable and reinstall the battery.
- Press the power button. The device should boot into the new firmware.

## Firmware Downloads

Various versions of the firmware can be found at the following links:

- 1.0.04: https://file.insta360.com/static/infr_base/759b2362289c483a24023d6f75e79bae/Insta360X3FW.bin
- 1.0.35: https://file.insta360.com/static/0cf8f2f16c5ed40cc1c00f726bd096ca/Insta360X3FW.bin
- 1.0.60 (firmware file shows 1.0.64): https://file.insta360.com/static/4286bca060822d118bbd19cd05dee402/Insta360X3FW.bin
- 1.0.66: https://file.insta360.com/static/b06b9cf93e5c220474fa95f4b0f2a289/Insta360X3FW.bin
- 1.0.69: https://file.insta360.com/static/ca3e39a00b14ed0ec6057d6433854298/Insta360X3FW.bin
- 1.0.80: https://file.insta360.com/static/16a29a8ecb7c46cb41d27df92819c28b/Insta360X3FW.bin
