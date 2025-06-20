#!/usr/bin/env bash
set -e

ROOTFS="$PWD/rootfs"
CMD="${*/bin/bash}"


# 1. Unshare namespaces
sudo unshare \
  --mount --uts --ipc --net --pid --fork \
  --mount-proc \
  bash -c "\
    # 2. Set hostname inside container
    hostname container1; \
    # 3. Chroot into our rootfs
    chroot $ROOTFS $CMD"
