#!/bin/bash

echo "=== MyDocker Demo ==="
echo "This demo showcases the Docker clone functionality"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This demo requires root privileges"
    echo "Please run: sudo ./demo.sh"
    exit 1
fi

echo "1. Creating base images..."
python3 -c "
from core.image import ImageManager
im = ImageManager()
im.create_base_images()
print('Base images created successfully!')
"

echo ""
echo "2. Listing available images..."
./mydocker.py images

echo ""
echo "3. Building a custom image from Dockerfile..."
./mydocker.py build -t myapp:latest -f Dockerfile.example .

echo ""
echo "4. Listing images after build..."
./mydocker.py images

echo ""
echo "5. Running a container..."
echo "Note: Container will run in background for demo"
CONTAINER_ID=$(./mydocker.py run -d alpine:latest /bin/sh -c "sleep 30; echo 'Container finished'")
echo "Container ID: $CONTAINER_ID"

echo ""
echo "6. Listing running containers..."
./mydocker.py ps

echo ""
echo "7. Testing pull functionality..."
./mydocker.py pull ubuntu:latest

echo ""
echo "8. Final image list..."
./mydocker.py images

echo ""
echo "=== Demo completed successfully! ==="
echo ""
echo "Available commands:"
echo "  ./mydocker.py pull <image>     - Pull an image"
echo "  ./mydocker.py run <image>      - Run a container"
echo "  ./mydocker.py build -t <tag> . - Build from Dockerfile"
echo "  ./mydocker.py ps               - List containers"
echo "  ./mydocker.py images           - List images"
echo "  ./mydocker.py stop <id>        - Stop container"
echo "  ./mydocker.py rm <id>          - Remove container"