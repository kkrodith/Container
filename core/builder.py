"""
Dockerfile parser and image builder
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image import ImageManager
from utils.filesystem import create_minimal_rootfs

class ImageBuilder:
    def __init__(self, storage_path="./storage"):
        self.storage_path = Path(storage_path).resolve()
        self.image_manager = ImageManager(storage_path)
        
        # Build cache directory
        self.build_cache = self.storage_path / "build_cache"
        self.build_cache.mkdir(exist_ok=True)
    
    def build_image(self, dockerfile_path="Dockerfile", context_path=".", tag=None):
        """
        Build an image from a Dockerfile
        
        Args:
            dockerfile_path: Path to Dockerfile
            context_path: Build context directory
            tag: Tag for the resulting image
        """
        print(f"Building image from {dockerfile_path}")
        
        # Parse Dockerfile
        dockerfile_full_path = Path(context_path) / dockerfile_path
        if not dockerfile_full_path.exists():
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile_full_path}")
        
        instructions = self._parse_dockerfile(dockerfile_full_path)
        
        # Create build directory
        with tempfile.TemporaryDirectory() as build_dir:
            build_path = Path(build_dir)
            image_path = build_path / "image"
            
            # Execute build instructions
            self._execute_build(instructions, context_path, image_path)
            
            # Store the built image
            if tag:
                image_id = self.image_manager.store_image(tag, image_path)
                return image_id
            else:
                # Generate temporary tag
                temp_tag = f"temp:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                image_id = self.image_manager.store_image(temp_tag, image_path)
                return image_id
    
    def _parse_dockerfile(self, dockerfile_path):
        """Parse Dockerfile and return list of instructions"""
        instructions = []
        
        with open(dockerfile_path, 'r') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Handle line continuations
            while line.endswith('\\'):
                line = line[:-1] + ' ' + lines[line_num].strip()
                line_num += 1
            
            # Parse instruction
            if ' ' in line:
                command, args = line.split(' ', 1)
            else:
                command, args = line, ''
            
            instructions.append({
                'command': command.upper(),
                'args': args,
                'line': line_num
            })
        
        return instructions
    
    def _execute_build(self, instructions, context_path, image_path):
        """Execute build instructions to create image"""
        # Start with base image or minimal rootfs
        base_image = None
        
        # Track image metadata
        image_config = {
            'Cmd': ['/bin/sh'],
            'WorkingDir': '/',
            'Env': ['PATH=/bin:/sbin:/usr/bin:/usr/sbin'],
            'ExposedPorts': {},
            'Volumes': {}
        }
        
        for instruction in instructions:
            print(f"Step: {instruction['command']} {instruction['args']}")
            
            if instruction['command'] == 'FROM':
                base_image = instruction['args']
                self._handle_from(base_image, image_path)
                
            elif instruction['command'] == 'RUN':
                self._handle_run(instruction['args'], image_path)
                
            elif instruction['command'] == 'COPY':
                self._handle_copy(instruction['args'], context_path, image_path)
                
            elif instruction['command'] == 'ADD':
                self._handle_add(instruction['args'], context_path, image_path)
                
            elif instruction['command'] == 'WORKDIR':
                image_config['WorkingDir'] = instruction['args']
                self._handle_workdir(instruction['args'], image_path)
                
            elif instruction['command'] == 'ENV':
                self._handle_env(instruction['args'], image_config)
                
            elif instruction['command'] == 'EXPOSE':
                self._handle_expose(instruction['args'], image_config)
                
            elif instruction['command'] == 'VOLUME':
                self._handle_volume(instruction['args'], image_config)
                
            elif instruction['command'] == 'CMD':
                image_config['Cmd'] = self._parse_command(instruction['args'])
                
            elif instruction['command'] == 'ENTRYPOINT':
                image_config['Entrypoint'] = self._parse_command(instruction['args'])
                
            elif instruction['command'] == 'USER':
                image_config['User'] = instruction['args']
                
            elif instruction['command'] == 'LABEL':
                if 'Labels' not in image_config:
                    image_config['Labels'] = {}
                self._handle_label(instruction['args'], image_config)
                
            else:
                print(f"Warning: Unsupported instruction {instruction['command']}")
        
        # Save image config
        config_file = image_path / '.mydocker_config'
        with open(config_file, 'w') as f:
            json.dump(image_config, f, indent=2)
    
    def _handle_from(self, base_image, image_path):
        """Handle FROM instruction"""
        if base_image.lower() == 'scratch':
            # Start from empty filesystem
            image_path.mkdir(parents=True, exist_ok=True)
        else:
            # Use base image
            if self.image_manager.image_exists(base_image):
                # Copy from local image
                base_path = self.image_manager.get_image_path(base_image)
                shutil.copytree(base_path, image_path, dirs_exist_ok=True)
            else:
                # Try to pull base image
                print(f"Base image {base_image} not found locally, pulling...")
                from core.registry import RegistryManager
                registry = RegistryManager(self.storage_path)
                registry.pull_image(base_image)
                
                # Now copy from local image
                base_path = self.image_manager.get_image_path(base_image)
                shutil.copytree(base_path, image_path, dirs_exist_ok=True)
    
    def _handle_run(self, command, image_path):
        """Handle RUN instruction"""
        # Execute command in chroot environment
        print(f"Running: {command}")
        
        # Create a script to run the command
        script_content = f"""#!/bin/bash
set -e
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
cd /
{command}
"""
        
        script_file = image_path / 'build_script.sh'
        script_file.write_text(script_content)
        script_file.chmod(0o755)
        
        try:
            # Execute in chroot (simplified - real implementation would use proper isolation)
            subprocess.run([
                'chroot', str(image_path), '/build_script.sh'
            ], check=True, capture_output=True, text=True)
            
        except subprocess.CalledProcessError as e:
            print(f"RUN command failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            # Continue with build for demo purposes
        
        finally:
            # Clean up script
            if script_file.exists():
                script_file.unlink()
    
    def _handle_copy(self, args, context_path, image_path):
        """Handle COPY instruction"""
        parts = args.split()
        if len(parts) < 2:
            raise ValueError(f"COPY requires at least 2 arguments, got: {args}")
        
        sources = parts[:-1]
        dest = parts[-1]
        
        # Ensure destination is absolute path in container
        if not dest.startswith('/'):
            dest = '/' + dest
        
        dest_path = image_path / dest.lstrip('/')
        
        for source in sources:
            source_path = Path(context_path) / source
            
            if source_path.exists():
                if source_path.is_file():
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                elif source_path.is_dir():
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            else:
                print(f"Warning: Source file not found: {source_path}")
    
    def _handle_add(self, args, context_path, image_path):
        """Handle ADD instruction (similar to COPY for now)"""
        # ADD has additional features like URL download and tar extraction
        # For simplicity, treating it like COPY
        self._handle_copy(args, context_path, image_path)
    
    def _handle_workdir(self, workdir, image_path):
        """Handle WORKDIR instruction"""
        if not workdir.startswith('/'):
            workdir = '/' + workdir
        
        workdir_path = image_path / workdir.lstrip('/')
        workdir_path.mkdir(parents=True, exist_ok=True)
    
    def _handle_env(self, args, image_config):
        """Handle ENV instruction"""
        if '=' in args:
            # ENV key=value format
            key, value = args.split('=', 1)
            env_var = f"{key.strip()}={value.strip()}"
        else:
            # ENV key value format
            parts = args.split(' ', 1)
            if len(parts) == 2:
                env_var = f"{parts[0]}={parts[1]}"
            else:
                return
        
        # Add to environment
        if 'Env' not in image_config:
            image_config['Env'] = []
        
        # Remove existing variable with same key
        key_name = env_var.split('=')[0]
        image_config['Env'] = [e for e in image_config['Env'] if not e.startswith(f"{key_name}=")]
        image_config['Env'].append(env_var)
    
    def _handle_expose(self, args, image_config):
        """Handle EXPOSE instruction"""
        ports = args.split()
        for port in ports:
            if '/' in port:
                port_num, protocol = port.split('/')
            else:
                port_num, protocol = port, 'tcp'
            
            image_config['ExposedPorts'][f"{port_num}/{protocol}"] = {}
    
    def _handle_volume(self, args, image_config):
        """Handle VOLUME instruction"""
        # Parse volume paths
        if args.startswith('[') and args.endswith(']'):
            # JSON array format
            import json
            volumes = json.loads(args)
        else:
            # Space-separated format
            volumes = args.split()
        
        for volume in volumes:
            image_config['Volumes'][volume] = {}
    
    def _handle_label(self, args, image_config):
        """Handle LABEL instruction"""
        if '=' in args:
            key, value = args.split('=', 1)
            image_config['Labels'][key.strip()] = value.strip().strip('"')
    
    def _parse_command(self, args):
        """Parse command arguments (CMD/ENTRYPOINT)"""
        args = args.strip()
        
        if args.startswith('[') and args.endswith(']'):
            # JSON array format
            import json
            return json.loads(args)
        else:
            # Shell format - convert to exec format
            return ['/bin/sh', '-c', args]
    
    def list_build_history(self):
        """List build history"""
        # Mock implementation
        return [
            {
                'id': 'build001',
                'tag': 'myapp:latest',
                'created': '2024-01-01 12:00:00',
                'size': '50MB'
            }
        ]
    
    def cleanup_build_cache(self):
        """Clean up build cache"""
        if self.build_cache.exists():
            shutil.rmtree(self.build_cache)
            self.build_cache.mkdir(exist_ok=True)
        print("Build cache cleaned")