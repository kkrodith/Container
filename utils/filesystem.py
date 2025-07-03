"""
Filesystem utilities for container operations
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import tarfile
import json

def create_overlay_mount(lower_dir, upper_dir, work_dir, merged_dir):
    """
    Create an overlay mount for container filesystem
    
    Args:
        lower_dir: Read-only base layer (image)
        upper_dir: Read-write layer (container changes)
        work_dir: Work directory for overlay
        merged_dir: Mount point for merged filesystem
    """
    # Ensure all directories exist
    Path(upper_dir).mkdir(parents=True, exist_ok=True)
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    Path(merged_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # Create overlay mount
        subprocess.run([
            'mount', '-t', 'overlay', 'overlay',
            '-o', f'lowerdir={lower_dir},upperdir={upper_dir},workdir={work_dir}',
            merged_dir
        ], check=True)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Failed to create overlay mount: {e}")
        return False

def unmount_overlay(mount_point):
    """Unmount overlay filesystem"""
    try:
        subprocess.run(['umount', mount_point], check=True)
        return True
    except subprocess.CalledProcessError:
        # Try force unmount
        try:
            subprocess.run(['umount', '-f', mount_point], check=True)
            return True
        except subprocess.CalledProcessError:
            return False

def setup_container_rootfs(image_path, container_id, storage_path):
    """
    Setup container root filesystem using overlay
    
    Returns:
        dict: Filesystem paths for the container
    """
    container_dir = Path(storage_path) / "containers" / container_id
    
    # Create container directories
    lower_dir = container_dir / "lower"
    upper_dir = container_dir / "upper"
    work_dir = container_dir / "work"
    merged_dir = container_dir / "merged"
    
    # Extract image to lower directory
    if not lower_dir.exists():
        lower_dir.mkdir(parents=True, exist_ok=True)
        extract_image(image_path, lower_dir)
    
    # Create overlay mount
    if create_overlay_mount(lower_dir, upper_dir, work_dir, merged_dir):
        return {
            'lower': str(lower_dir),
            'upper': str(upper_dir),
            'work': str(work_dir),
            'merged': str(merged_dir),
            'container_dir': str(container_dir)
        }
    else:
        # Fallback to simple copy
        if not merged_dir.exists():
            shutil.copytree(lower_dir, merged_dir)
        return {
            'merged': str(merged_dir),
            'container_dir': str(container_dir)
        }

def extract_image(image_path, target_dir):
    """Extract container image to directory"""
    image_file = Path(image_path)
    
    if not image_file.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    if image_file.suffix == '.tar':
        # Extract tar file
        with tarfile.open(image_file, 'r') as tar:
            tar.extractall(target_dir)
    else:
        # Assume it's a directory
        if image_file.is_dir():
            shutil.copytree(image_file, target_dir, dirs_exist_ok=True)
        else:
            raise ValueError(f"Unsupported image format: {image_path}")

def create_minimal_rootfs(target_dir):
    """Create a minimal root filesystem"""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    
    # Essential directories
    essential_dirs = [
        'bin', 'sbin', 'usr/bin', 'usr/sbin', 'lib', 'lib64',
        'etc', 'dev', 'proc', 'sys', 'tmp', 'var', 'home', 'root'
    ]
    
    for dir_name in essential_dirs:
        (target / dir_name).mkdir(parents=True, exist_ok=True)
    
    # Copy essential binaries from host
    copy_essential_binaries(target)
    
    # Create basic device files
    create_device_files(target / 'dev')
    
    # Create basic configuration files
    create_basic_config_files(target)

def copy_essential_binaries(rootfs):
    """Copy essential binaries to container rootfs"""
    essential_bins = [
        '/bin/sh', '/bin/bash', '/bin/ls', '/bin/cat', '/bin/echo',
        '/bin/ps', '/bin/kill', '/usr/bin/which', '/usr/bin/env'
    ]
    
    bin_dir = rootfs / 'bin'
    
    for binary in essential_bins:
        if os.path.exists(binary):
            try:
                shutil.copy2(binary, bin_dir / os.path.basename(binary))
                
                # Copy dependencies (simplified)
                copy_binary_dependencies(binary, rootfs)
                
            except (PermissionError, shutil.SameFileError):
                pass

def copy_binary_dependencies(binary, rootfs):
    """Copy shared library dependencies"""
    try:
        # Get library dependencies using ldd
        result = subprocess.run(['ldd', binary], capture_output=True, text=True)
        
        for line in result.stdout.split('\n'):
            if '=>' in line:
                parts = line.split('=>')
                if len(parts) > 1:
                    lib_path = parts[1].strip().split()[0]
                    if lib_path.startswith('/'):
                        lib_name = os.path.basename(lib_path)
                        
                        # Determine target directory
                        if 'lib64' in lib_path:
                            target_dir = rootfs / 'lib64'
                        else:
                            target_dir = rootfs / 'lib'
                        
                        target_dir.mkdir(parents=True, exist_ok=True)
                        
                        try:
                            shutil.copy2(lib_path, target_dir / lib_name)
                        except (FileNotFoundError, PermissionError, shutil.SameFileError):
                            pass
                            
    except subprocess.CalledProcessError:
        pass

def create_device_files(dev_dir):
    """Create basic device files"""
    devices = [
        ('null', 'c', 1, 3),
        ('zero', 'c', 1, 5),
        ('random', 'c', 1, 8),
        ('urandom', 'c', 1, 9),
    ]
    
    for name, dev_type, major, minor in devices:
        device_path = dev_dir / name
        try:
            if dev_type == 'c':
                os.mknod(device_path, 0o666 | 0o020000, os.makedev(major, minor))
        except (PermissionError, FileExistsError):
            pass

def create_basic_config_files(rootfs):
    """Create basic configuration files"""
    # /etc/passwd
    passwd_content = """root:x:0:0:root:/root:/bin/sh
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
"""
    (rootfs / 'etc' / 'passwd').write_text(passwd_content)
    
    # /etc/group
    group_content = """root:x:0:
nogroup:x:65534:
"""
    (rootfs / 'etc' / 'group').write_text(group_content)
    
    # /etc/hosts
    hosts_content = """127.0.0.1 localhost
::1 localhost ip6-localhost ip6-loopback
"""
    (rootfs / 'etc' / 'hosts').write_text(hosts_content)
    
    # /etc/resolv.conf
    resolv_content = """nameserver 8.8.8.8
nameserver 8.8.4.4
"""
    (rootfs / 'etc' / 'resolv.conf').write_text(resolv_content)

def bind_mount(source, target, readonly=False):
    """Create bind mount"""
    try:
        Path(target).mkdir(parents=True, exist_ok=True)
        
        cmd = ['mount', '--bind', source, target]
        subprocess.run(cmd, check=True)
        
        if readonly:
            subprocess.run(['mount', '-o', 'remount,ro', target], check=True)
        
        return True
        
    except subprocess.CalledProcessError:
        return False

def cleanup_mounts(mount_points):
    """Cleanup multiple mount points"""
    for mount_point in reversed(mount_points):  # Unmount in reverse order
        try:
            subprocess.run(['umount', mount_point], 
                         stderr=subprocess.DEVNULL, check=False)
        except:
            pass

def get_mount_info(path):
    """Get mount information for a path"""
    try:
        result = subprocess.run(['findmnt', '-n', '-o', 'SOURCE,FSTYPE', path], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            return {
                'source': parts[0] if parts else None,
                'fstype': parts[1] if len(parts) > 1 else None
            }
    except:
        pass
    
    return {'source': None, 'fstype': None}

def calculate_directory_size(path):
    """Calculate total size of directory"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, PermissionError):
        pass
    
    return total_size

def format_size(bytes_size):
    """Format size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f}PB"