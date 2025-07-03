"""
Registry operations for pulling and pushing images
"""

import os
import sys
import json
import tarfile
import tempfile
from pathlib import Path

# Optional import for requests - fallback if not available
try:
    import requests
    from urllib.parse import urlparse
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests module not available, registry operations will be limited")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image import ImageManager

class RegistryManager:
    def __init__(self, storage_path="./storage"):
        self.storage_path = Path(storage_path).resolve()
        self.image_manager = ImageManager(storage_path)
        
        # Default registry configuration
        self.default_registry = "registry-1.docker.io"
        self.registry_configs = {
            "registry-1.docker.io": {
                "url": "https://registry-1.docker.io",
                "auth_url": "https://auth.docker.io/token",
                "service": "registry.docker.io"
            }
        }
    
    def pull_image(self, image_name):
        """
        Pull an image from registry
        
        This is a simplified implementation that creates mock images
        since we can't actually connect to Docker Hub without proper authentication
        """
        print(f"Pulling image: {image_name}")
        
        # Parse image name
        repository, tag = self._parse_image_name(image_name)
        
        # For this demo, we'll create/ensure basic images exist
        if repository in ['alpine', 'ubuntu', 'busybox', 'debian', 'centos']:
            self._create_mock_image(image_name, repository, tag)
        else:
            # Try to download from a real registry (simplified)
            try:
                self._download_from_registry(image_name, repository, tag)
            except Exception as e:
                print(f"Failed to pull from registry: {e}")
                print("Creating mock image instead...")
                self._create_mock_image(image_name, repository, tag)
        
        print(f"Successfully pulled {image_name}")
    
    def push_image(self, image_name, registry_url=None):
        """
        Push an image to registry (mock implementation)
        """
        if not self.image_manager.image_exists(image_name):
            raise FileNotFoundError(f"Image {image_name} not found locally")
        
        print(f"Pushing image: {image_name}")
        
        if registry_url is None:
            registry_url = self.default_registry
        
        # In a real implementation, this would:
        # 1. Authenticate with the registry
        # 2. Upload image layers
        # 3. Upload manifest
        
        print(f"Mock: Image {image_name} pushed to {registry_url}")
    
    def _parse_image_name(self, image_name):
        """Parse image name into repository and tag"""
        if ':' in image_name:
            repository, tag = image_name.rsplit(':', 1)
        else:
            repository = image_name
            tag = 'latest'
        
        return repository, tag
    
    def _create_mock_image(self, image_name, repository, tag):
        """Create a mock image for common base images"""
        print(f"Creating mock image for {image_name}")
        
        # Define mock image configurations
        mock_configs = {
            'alpine': {
                'base_cmd': ['/bin/sh'],
                'description': 'Alpine Linux minimal image',
                'env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin']
            },
            'ubuntu': {
                'base_cmd': ['/bin/bash'],
                'description': 'Ubuntu base image',
                'env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin', 'DEBIAN_FRONTEND=noninteractive']
            },
            'busybox': {
                'base_cmd': ['/bin/sh'],
                'description': 'BusyBox minimal utilities',
                'env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin']
            },
            'debian': {
                'base_cmd': ['/bin/bash'],
                'description': 'Debian base image',
                'env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin', 'DEBIAN_FRONTEND=noninteractive']
            },
            'centos': {
                'base_cmd': ['/bin/bash'],
                'description': 'CentOS base image',
                'env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin']
            }
        }
        
        config = mock_configs.get(repository, mock_configs['alpine'])
        
        # Create temporary directory for image
        with tempfile.TemporaryDirectory() as temp_dir:
            image_dir = Path(temp_dir) / "rootfs"
            
            # Create minimal filesystem
            from utils.filesystem import create_minimal_rootfs
            create_minimal_rootfs(image_dir)
            
            # Add some repository-specific files
            self._customize_mock_image(image_dir, repository)
            
            # Store the image
            image_config = {
                'Cmd': config['base_cmd'],
                'WorkingDir': '/',
                'Env': config['env'],
                'Description': config['description']
            }
            
            self.image_manager.store_image(image_name, image_dir, image_config)
    
    def _customize_mock_image(self, image_dir, repository):
        """Add repository-specific customizations"""
        # Create OS release file
        os_release_content = {
            'alpine': 'NAME="Alpine Linux"\nVERSION_ID="3.17"\nID=alpine\n',
            'ubuntu': 'NAME="Ubuntu"\nVERSION="20.04 LTS"\nID=ubuntu\n',
            'debian': 'NAME="Debian GNU/Linux"\nVERSION_ID="11"\nID=debian\n',
            'centos': 'NAME="CentOS Linux"\nVERSION_ID="8"\nID=centos\n',
            'busybox': 'NAME="BusyBox"\nVERSION_ID="1.35"\nID=busybox\n'
        }
        
        release_content = os_release_content.get(repository, os_release_content['alpine'])
        
        os_release_file = image_dir / 'etc' / 'os-release'
        os_release_file.parent.mkdir(parents=True, exist_ok=True)
        os_release_file.write_text(release_content)
        
        # Add package manager placeholders
        if repository in ['ubuntu', 'debian']:
            apt_dir = image_dir / 'usr' / 'bin'
            apt_dir.mkdir(parents=True, exist_ok=True)
            
            # Create dummy apt command
            apt_script = """#!/bin/sh
echo "Mock apt package manager"
echo "Available commands: update, install, remove"
case "$1" in
    update) echo "Package lists updated" ;;
    install) echo "Mock installing: $*" ;;
    remove) echo "Mock removing: $*" ;;
    *) echo "Usage: apt {update|install|remove} [packages...]" ;;
esac
"""
            (apt_dir / 'apt').write_text(apt_script)
            (apt_dir / 'apt').chmod(0o755)
            
        elif repository == 'alpine':
            apk_dir = image_dir / 'sbin'
            apk_dir.mkdir(parents=True, exist_ok=True)
            
            # Create dummy apk command
            apk_script = """#!/bin/sh
echo "Mock apk package manager"
echo "Available commands: update, add, del"
case "$1" in
    update) echo "Package index updated" ;;
    add) echo "Mock installing: $*" ;;
    del) echo "Mock removing: $*" ;;
    *) echo "Usage: apk {update|add|del} [packages...]" ;;
esac
"""
            (apk_dir / 'apk').write_text(apk_script)
            (apk_dir / 'apk').chmod(0o755)
    
    def _download_from_registry(self, image_name, repository, tag):
        """
        Download image from actual registry (simplified implementation)
        """
        if not HAS_REQUESTS:
            raise Exception("requests module not available for registry operations")
        
        # This is a very simplified version of Docker registry protocol
        # Real implementation would need proper authentication, manifest parsing, etc.
        
        registry_url = self.registry_configs[self.default_registry]["url"]
        
        # Try to get manifest (this will likely fail without proper auth)
        manifest_url = f"{registry_url}/v2/{repository}/manifests/{tag}"
        
        try:
            response = requests.get(manifest_url, timeout=10)
            response.raise_for_status()
            
            # If we got here, we could implement proper layer downloading
            # For now, just fall back to mock image
            raise NotImplementedError("Full registry protocol not implemented")
            
        except requests.RequestException:
            # Expected to fail - fall back to mock
            raise Exception("Registry connection failed")
    
    def search_images(self, query):
        """Search for images in registry (mock implementation)"""
        # Mock search results
        mock_results = [
            {'name': f'{query}:latest', 'description': f'Official {query} image'},
            {'name': f'{query}:alpine', 'description': f'{query} on Alpine Linux'},
            {'name': f'{query}:slim', 'description': f'Slim {query} image'},
        ]
        
        return mock_results
    
    def login(self, registry_url, username, password):
        """Login to registry (mock implementation)"""
        print(f"Mock login to {registry_url} as {username}")
        # In real implementation, would store auth token
        return True
    
    def logout(self, registry_url):
        """Logout from registry"""
        print(f"Mock logout from {registry_url}")
        return True
    
    def list_tags(self, repository):
        """List available tags for a repository"""
        # Mock implementation
        mock_tags = ['latest', 'alpine', 'slim', '3.17', '20.04', '18.04']
        return mock_tags
    
    def get_image_manifest(self, image_name):
        """Get image manifest from registry"""
        # Mock manifest
        repository, tag = self._parse_image_name(image_name)
        
        mock_manifest = {
            'schemaVersion': 2,
            'mediaType': 'application/vnd.docker.distribution.manifest.v2+json',
            'config': {
                'mediaType': 'application/vnd.docker.container.image.v1+json',
                'size': 1024,
                'digest': f'sha256:{"0" * 64}'
            },
            'layers': [
                {
                    'mediaType': 'application/vnd.docker.image.rootfs.diff.tar.gzip',
                    'size': 2048000,
                    'digest': f'sha256:{"1" * 64}'
                }
            ]
        }
        
        return mock_manifest