#!/usr/bin/env bash
# Enhanced container script - now part of MyDocker system
set -e

# Configuration
ROOTFS="$PWD/storage/images/alpine_latest"
CMD="${*:-/bin/bash}"
CONTAINER_ID=$(date +%s)

echo "=== MyDocker Legacy Container Runner ==="
echo "Container ID: $CONTAINER_ID"
echo "Rootfs: $ROOTFS"
echo "Command: $CMD"

# Check if rootfs exists, if not create it
if [ ! -d "$ROOTFS" ]; then
    echo "Creating minimal rootfs..."
    mkdir -p storage/images
    echo "Using MyDocker to create base image..."
    python3 -c "
from core.image import ImageManager
im = ImageManager()
im.create_base_images()
print('Base images created!')
    " 2>/dev/null || {
        echo "Warning: Could not create base images via MyDocker"
        echo "Creating minimal rootfs manually..."
        mkdir -p "$ROOTFS"/{bin,sbin,etc,proc,sys,dev,tmp,var,usr/bin,usr/sbin}
        
        # Copy essential binaries if available
        for bin in /bin/sh /bin/bash /bin/ls /bin/cat; do
            if [ -f "$bin" ]; then
                cp "$bin" "$ROOTFS/bin/" 2>/dev/null || true
            fi
        done
        
        # Create basic passwd
        echo "root:x:0:0:root:/root:/bin/sh" > "$ROOTFS/etc/passwd"
    }
fi

echo "Starting container with enhanced isolation..."

# 1. Unshare namespaces (enhanced version)
sudo unshare \
  --mount --uts --ipc --net --pid --fork \
  --mount-proc \
  bash -c "
    # Set up container environment
    echo 'Setting up container environment...'
    
    # 2. Set hostname inside container
    hostname container-$CONTAINER_ID
    
    # 3. Mount essential filesystems
    mount -t proc proc $ROOTFS/proc 2>/dev/null || true
    mount -t sysfs sysfs $ROOTFS/sys 2>/dev/null || true
    mount -t tmpfs tmpfs $ROOTFS/tmp 2>/dev/null || true
    
    # 4. Setup basic devices
    mkdir -p $ROOTFS/dev
    mknod $ROOTFS/dev/null c 1 3 2>/dev/null || true
    mknod $ROOTFS/dev/zero c 1 5 2>/dev/null || true
    
    echo 'Container environment ready!'
    echo 'Entering container...'
    echo '========================'
    
    # 5. Chroot into our rootfs and execute command
    chroot $ROOTFS $CMD || {
        echo 'Command failed, dropping to shell...'
        chroot $ROOTFS /bin/sh
    }
    
    echo '========================'
    echo 'Container exited'
"

echo "Container $CONTAINER_ID finished"
