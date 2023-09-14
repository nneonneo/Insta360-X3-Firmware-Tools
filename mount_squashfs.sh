#!/bin/bash

if [ $# -ne 2 ]; then
  echo "Usage: $0 <squashfs> <mount_prefix>"
  exit
fi

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit
fi

squash_img="$1"
mount_prefix="$2"

if [ -e "${mount_prefix}/etc" ]; then
  echo "squashfs appears to already be mounted!"
  exit
fi

mkdir -p "${mount_prefix}_lower"
mkdir -p "${mount_prefix}_upper"
mkdir -p "${mount_prefix}_work"
mkdir -p "${mount_prefix}"

mount -t squashfs "${squash_img}" "${mount_prefix}_lower"
mount -t overlay none -olowerdir="${mount_prefix}_lower",upperdir="${mount_prefix}_upper",workdir="${mount_prefix}_work" "${mount_prefix}"

echo "Done. When finished, you can use 'mksquashfs ${mount_prefix} ${squash_img}.new -comp lzo -b 128k -noappend', then 'umount ${mount_prefix}' and 'umount ${mount_prefix}_lower'."
