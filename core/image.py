"""
Image management and storage
"""

import os
import sys
import json
import shutil
import tarfile
import hashlib
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.filesystem import calculate_directory_size, format_size, create_minimal_rootfs

class ImageManager:
    def __init__(self, storage_path="./storage"):
        self.storage_path = Path(storage_path).resolve()
        self.images_dir = self.storage_path / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Image metadata storage
        self.image_metadata_file = self.images_dir / "metadata.json"
        self._load_image_metadata()
    
    def _load_image_metadata(self):
        """Load image metadata from storage"""
        if self.image_metadata_file.exists():
            with open(self.image_metadata_file, 'r') as f:
                self.image_metadata = json.load(f)
        else:
            self.image_metadata = {}
    
    def _save_image_metadata(self):
        """Save image metadata to storage"""
        with open(self.image_metadata_file, 'w') as f:
            json.dump(self.image_metadata, f, indent=2)
    
    def image_exists(self, image_name):
        """Check if image exists locally"""
        return image_name in self.image_metadata
    
    def store_image(self, image_name, image_path, image_config=None):
        """
        Store an image in local storage
        
        Args:
            image_name: Name of the image (e.g., "ubuntu:20.04")
            image_path: Path to image data (tar file or directory)
            image_config: Optional image configuration
        """
        print(f"Storing image: {image_name}")
        
        # Create image storage directory
        safe_name = image_name.replace(':', '_').replace('/', '_')
        image_dir = self.images_dir / safe_name
        image_dir.mkdir(exist_ok=True)
        
        # Extract or copy image data
        if Path(image_path).is_file() and image_path.endswith('.tar'):
            # Extract tar file
            with tarfile.open(image_path, 'r') as tar:
                tar.extractall(image_dir)
        elif Path(image_path).is_dir():
            # Copy directory
            for item in Path(image_path).iterdir():
                if item.is_dir():
                    shutil.copytree(item, image_dir / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, image_dir)
        else:
            raise ValueError(f"Unsupported image format: {image_path}")
        
        # Calculate image size
        image_size = calculate_directory_size(image_dir)
        
        # Generate image ID
        image_id = self._generate_image_id(image_dir)
        
        # Store metadata
        self.image_metadata[image_name] = {
            'id': image_id,
            'repository': image_name.split(':')[0],
            'tag': image_name.split(':')[1] if ':' in image_name else 'latest',
            'created': datetime.now().isoformat(),
            'size': image_size,
            'path': str(image_dir),
            'config': image_config or {}
        }
        
        self._save_image_metadata()
        print(f"Image {image_name} stored with ID {image_id}")
        
        return image_id
    
    def create_base_images(self):
        """Create basic base images for testing"""
        # Create Alpine-like minimal image
        alpine_dir = self.images_dir / "alpine_latest"
        if not alpine_dir.exists():
            print("Creating minimal alpine:latest image...")
            create_minimal_rootfs(alpine_dir)
            
            self.image_metadata["alpine:latest"] = {
                'id': self._generate_image_id(alpine_dir),
                'repository': 'alpine',
                'tag': 'latest',
                'created': datetime.now().isoformat(),
                'size': calculate_directory_size(alpine_dir),
                'path': str(alpine_dir),
                'config': {
                    'Cmd': ['/bin/sh'],
                    'WorkingDir': '/',
                    'Env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin']
                }
            }
        
        # Create Ubuntu-like image (just a copy of alpine for simplicity)
        ubuntu_dir = self.images_dir / "ubuntu_latest"
        if not ubuntu_dir.exists():
            print("Creating minimal ubuntu:latest image...")
            if alpine_dir.exists():
                shutil.copytree(alpine_dir, ubuntu_dir)
            else:
                create_minimal_rootfs(ubuntu_dir)
            
            self.image_metadata["ubuntu:latest"] = {
                'id': self._generate_image_id(ubuntu_dir),
                'repository': 'ubuntu',
                'tag': 'latest',
                'created': datetime.now().isoformat(),
                'size': calculate_directory_size(ubuntu_dir),
                'path': str(ubuntu_dir),
                'config': {
                    'Cmd': ['/bin/bash'],
                    'WorkingDir': '/',
                    'Env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin']
                }
            }
        
        self._save_image_metadata()
    
    def list_images(self):
        """List all stored images"""
        images = []
        
        for image_name, metadata in self.image_metadata.items():
            images.append({
                'repository': metadata['repository'],
                'tag': metadata['tag'],
                'id': metadata['id'][:12],
                'created': metadata['created'][:19].replace('T', ' '),
                'size': format_size(metadata['size'])
            })
        
        return images
    
    def get_image_info(self, image_name):
        """Get detailed information about an image"""
        if image_name not in self.image_metadata:
            raise FileNotFoundError(f"Image {image_name} not found")
        
        return self.image_metadata[image_name]
    
    def remove_image(self, image_name, force=False):
        """Remove an image"""
        if image_name not in self.image_metadata:
            raise FileNotFoundError(f"Image {image_name} not found")
        
        # TODO: Check if image is being used by containers
        if not force:
            # Here we would check if any containers are using this image
            pass
        
        metadata = self.image_metadata[image_name]
        image_path = Path(metadata['path'])
        
        # Remove image directory
        if image_path.exists():
            shutil.rmtree(image_path)
        
        # Remove from metadata
        del self.image_metadata[image_name]
        self._save_image_metadata()
        
        print(f"Image {image_name} removed")
    
    def build_image_from_layers(self, layers, image_name):
        """
        Build image from multiple layers (simplified layer system)
        
        Args:
            layers: List of layer directories/files
            image_name: Name for the resulting image
        """
        print(f"Building image {image_name} from {len(layers)} layers")
        
        # Create image directory
        safe_name = image_name.replace(':', '_').replace('/', '_')
        image_dir = self.images_dir / safe_name
        image_dir.mkdir(exist_ok=True)
        
        # Apply layers in order
        for i, layer in enumerate(layers):
            print(f"Applying layer {i+1}/{len(layers)}")
            
            if Path(layer).is_file() and layer.endswith('.tar'):
                # Extract tar layer
                with tarfile.open(layer, 'r') as tar:
                    tar.extractall(image_dir)
            elif Path(layer).is_dir():
                # Copy directory layer
                for item in Path(layer).rglob('*'):
                    if item.is_file():
                        rel_path = item.relative_to(layer)
                        target_path = image_dir / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target_path)
        
        # Store the built image
        image_id = self.store_image(image_name, image_dir)
        return image_id
    
    def export_image(self, image_name, output_path):
        """Export image to tar file"""
        if image_name not in self.image_metadata:
            raise FileNotFoundError(f"Image {image_name} not found")
        
        metadata = self.image_metadata[image_name]
        image_path = Path(metadata['path'])
        
        print(f"Exporting image {image_name} to {output_path}")
        
        with tarfile.open(output_path, 'w') as tar:
            for item in image_path.rglob('*'):
                if item.is_file():
                    arcname = item.relative_to(image_path)
                    tar.add(item, arcname=arcname)
        
        print(f"Image exported to {output_path}")
    
    def import_image(self, tar_path, image_name):
        """Import image from tar file"""
        if not Path(tar_path).exists():
            raise FileNotFoundError(f"File {tar_path} not found")
        
        print(f"Importing image from {tar_path} as {image_name}")
        
        # Store the image
        image_id = self.store_image(image_name, tar_path)
        return image_id
    
    def _generate_image_id(self, image_path):
        """Generate unique image ID based on content"""
        hasher = hashlib.sha256()
        
        # Hash all files in the image directory
        for item in sorted(Path(image_path).rglob('*')):
            if item.is_file():
                try:
                    with open(item, 'rb') as f:
                        hasher.update(f.read())
                except (PermissionError, FileNotFoundError):
                    pass
        
        return hasher.hexdigest()[:12]
    
    def get_image_path(self, image_name):
        """Get filesystem path for an image"""
        if image_name not in self.image_metadata:
            raise FileNotFoundError(f"Image {image_name} not found")
        
        return self.image_metadata[image_name]['path']
    
    def tag_image(self, source_image, target_image):
        """Create a tag for an existing image"""
        if source_image not in self.image_metadata:
            raise FileNotFoundError(f"Image {source_image} not found")
        
        # Copy metadata with new name
        source_metadata = self.image_metadata[source_image].copy()
        source_metadata['repository'] = target_image.split(':')[0]
        source_metadata['tag'] = target_image.split(':')[1] if ':' in target_image else 'latest'
        
        self.image_metadata[target_image] = source_metadata
        self._save_image_metadata()
        
        print(f"Tagged {source_image} as {target_image}")
    
    def cleanup_dangling_images(self):
        """Remove dangling images (not referenced by any tag)"""
        # This is a simplified version - in a real implementation,
        # we would track layer usage across images
        pass