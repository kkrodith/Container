"""
Namespace utilities for container isolation
"""

import os
import ctypes
import ctypes.util
import subprocess
import signal
from pathlib import Path

# Namespace constants
CLONE_NEWNS = 0x00020000    # Mount namespace
CLONE_NEWUTS = 0x04000000   # UTS namespace
CLONE_NEWIPC = 0x08000000   # IPC namespace
CLONE_NEWPID = 0x20000000   # PID namespace
CLONE_NEWNET = 0x40000000   # Network namespace
CLONE_NEWUSER = 0x10000000  # User namespace

def check_privileges():
    """Check if running with root privileges"""
    return os.geteuid() == 0

def unshare_namespaces(namespaces=None):
    """
    Unshare specified namespaces
    """
    if namespaces is None:
        namespaces = CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWPID | CLONE_NEWNET
    
    libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
    
    if libc.unshare(namespaces) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"Failed to unshare namespaces: {os.strerror(errno)}")

def set_hostname(hostname):
    """Set hostname in UTS namespace"""
    try:
        with open('/proc/sys/kernel/hostname', 'w') as f:
            f.write(hostname)
    except PermissionError:
        # Fallback to hostname command
        subprocess.run(['hostname', hostname], check=True)

def mount_proc():
    """Mount /proc filesystem in PID namespace"""
    proc_path = Path('/proc')
    if proc_path.exists():
        # Unmount existing /proc
        subprocess.run(['umount', '/proc'], stderr=subprocess.DEVNULL)
    
    # Mount new /proc
    subprocess.run(['mount', '-t', 'proc', 'proc', '/proc'], check=True)

def setup_container_environment(container_id, hostname=None):
    """
    Setup complete container environment with all namespaces
    """
    if hostname is None:
        hostname = f"container-{container_id[:8]}"
    
    # Unshare all namespaces
    unshare_namespaces()
    
    # Set container hostname
    set_hostname(hostname)
    
    # Mount /proc in new PID namespace
    try:
        mount_proc()
    except subprocess.CalledProcessError:
        # /proc mount may fail in some environments, continue anyway
        pass

def create_network_namespace(container_id):
    """Create and configure network namespace"""
    ns_name = f"mydocker-{container_id[:8]}"
    
    try:
        # Create network namespace
        subprocess.run(['ip', 'netns', 'add', ns_name], check=True)
        
        # Create veth pair
        veth_host = f"veth-{container_id[:8]}"
        veth_container = f"vethin-{container_id[:8]}"
        
        subprocess.run([
            'ip', 'link', 'add', veth_host, 'type', 'veth', 'peer', 'name', veth_container
        ], check=True)
        
        # Move container veth to namespace
        subprocess.run([
            'ip', 'link', 'set', veth_container, 'netns', ns_name
        ], check=True)
        
        # Configure container network interface
        subprocess.run([
            'ip', 'netns', 'exec', ns_name, 'ip', 'addr', 'add', 
            f'172.17.0.{hash(container_id) % 254 + 2}/24', 'dev', veth_container
        ], check=True)
        
        subprocess.run([
            'ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', veth_container, 'up'
        ], check=True)
        
        subprocess.run([
            'ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'lo', 'up'
        ], check=True)
        
        return ns_name
        
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to setup network namespace: {e}")
        return None

def cleanup_network_namespace(ns_name):
    """Cleanup network namespace"""
    if ns_name:
        try:
            subprocess.run(['ip', 'netns', 'delete', ns_name], check=True)
        except subprocess.CalledProcessError:
            pass

def enter_namespace(pid, ns_type):
    """Enter a specific namespace of a running process"""
    ns_path = f"/proc/{pid}/ns/{ns_type}"
    
    if not os.path.exists(ns_path):
        raise FileNotFoundError(f"Namespace {ns_type} not found for PID {pid}")
    
    # This would typically require setns() syscall
    # For simplicity, we'll use nsenter command
    return ns_path

def kill_process_tree(pid):
    """Kill process and all its children"""
    try:
        # Get all child processes
        children = subprocess.check_output([
            'pgrep', '-P', str(pid)
        ], text=True).strip().split('\n')
        
        # Kill children first
        for child_pid in children:
            if child_pid:
                try:
                    os.kill(int(child_pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
        
        # Kill main process
        os.kill(pid, signal.SIGTERM)
        
        # Wait a bit, then force kill if necessary
        import time
        time.sleep(1)
        
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
            
    except (subprocess.CalledProcessError, ProcessLookupError, ValueError):
        pass