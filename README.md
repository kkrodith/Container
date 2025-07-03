# MyDocker - A Mini Docker Clone

A lightweight Docker clone implementation that provides core containerization functionality using Linux namespaces, cgroups, and overlay filesystems.

## Features

- **Container Management**: Create, start, stop, remove containers
- **Image Management**: Pull, build, and store container images
- **Registry Operations**: Pull images from registries (Docker Hub simulation)
- **Dockerfile Support**: Build images from Dockerfiles
- **Networking**: Basic container networking with isolated network namespaces
- **Volume Management**: Mount host directories into containers
- **Process Isolation**: Full process, network, and filesystem isolation
- **Resource Limits**: CPU and memory constraints using cgroups

## Architecture

```
mydocker/
├── mydocker.py          # Main CLI interface
├── core/
│   ├── container.py     # Container lifecycle management
│   ├── image.py         # Image management and storage
│   ├── network.py       # Network management
│   ├── registry.py      # Registry operations
│   └── builder.py       # Dockerfile parser and builder
├── storage/
│   ├── images/          # Image storage
│   ├── containers/      # Container storage
│   └── volumes/         # Volume storage
└── utils/
    ├── namespace.py     # Linux namespace utilities
    ├── cgroup.py        # cgroup management
    └── filesystem.py    # Filesystem operations

```

## Usage

```bash
# Pull an image
./mydocker.py pull alpine:latest

# Build an image from Dockerfile
./mydocker.py build -t myapp:latest .

# Run a container
./mydocker.py run -it alpine:latest /bin/sh

# List containers
./mydocker.py ps

# Stop a container
./mydocker.py stop <container_id>

# Remove a container
./mydocker.py rm <container_id>
```

## Requirements

- Linux kernel with namespace support
- Python 3.8+
- Root privileges (for namespace operations)
- overlayfs support

## Installation

```bash
chmod +x mydocker.py
sudo ./mydocker.py --help
```