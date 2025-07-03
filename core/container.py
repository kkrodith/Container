"""
Container lifecycle management
"""

import os
import sys
import json
import uuid
import subprocess
import signal
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.namespace import setup_container_environment, create_network_namespace, cleanup_network_namespace
from utils.cgroup import CgroupManager
from utils.filesystem import setup_container_rootfs, bind_mount, cleanup_mounts, unmount_overlay

class ContainerManager:
    def __init__(self, storage_path="./storage"):
        self.storage_path = Path(storage_path).resolve()
        self.containers_dir = self.storage_path / "containers"
        self.containers_dir.mkdir(parents=True, exist_ok=True)
        
        self.cgroup_manager = CgroupManager()
        self.running_containers = {}
    
    def create_container(self, image, command=None, interactive=False, 
                        volumes=None, environment=None, working_dir=None,
                        cpu_limit=None, memory_limit=None):
        """Create a new container"""
        
        container_id = str(uuid.uuid4())[:12]
        
        if command is None:
            command = ['/bin/sh']
        
        # Container metadata
        container_config = {
            'id': container_id,
            'image': image,
            'command': command,
            'interactive': interactive,
            'volumes': volumes or [],
            'environment': environment or [],
            'working_dir': working_dir or '/',
            'cpu_limit': cpu_limit,
            'memory_limit': memory_limit,
            'created': datetime.now().isoformat(),
            'status': 'created',
            'pid': None,
            'network_namespace': None
        }
        
        # Save container config
        container_file = self.containers_dir / f"{container_id}.json"
        with open(container_file, 'w') as f:
            json.dump(container_config, f, indent=2)
        
        return container_id
    
    def start_container(self, container_id):
        """Start a stopped container"""
        container_config = self._load_container_config(container_id)
        
        if container_config['status'] == 'running':
            print(f"Container {container_id} is already running")
            return
        
        # Update status
        container_config['status'] = 'starting'
        self._save_container_config(container_id, container_config)
        
        try:
            # Setup container environment
            self._setup_container(container_id, container_config)
            
            # Start container process
            pid = self._start_container_process(container_id, container_config)
            
            # Update container status
            container_config['status'] = 'running'
            container_config['pid'] = pid
            container_config['started'] = datetime.now().isoformat()
            self._save_container_config(container_id, container_config)
            
            self.running_containers[container_id] = pid
            
            print(f"Container {container_id} started with PID {pid}")
            
        except Exception as e:
            container_config['status'] = 'exited'
            self._save_container_config(container_id, container_config)
            raise e
    
    def run_container(self, container_id):
        """Run container in foreground (like docker run without -d)"""
        container_config = self._load_container_config(container_id)
        
        try:
            # Setup container environment
            self._setup_container(container_id, container_config)
            
            # Run container process in foreground
            self._run_container_process(container_id, container_config)
            
        except KeyboardInterrupt:
            print(f"\nStopping container {container_id}")
            self.stop_container(container_id)
        except Exception as e:
            print(f"Error running container: {e}")
            container_config['status'] = 'exited'
            self._save_container_config(container_id, container_config)
    
    def stop_container(self, container_id):
        """Stop a running container"""
        container_config = self._load_container_config(container_id)
        
        if container_config['status'] != 'running':
            print(f"Container {container_id} is not running")
            return
        
        pid = container_config.get('pid')
        if pid:
            try:
                # Send SIGTERM first
                os.kill(pid, signal.SIGTERM)
                
                # Wait for graceful shutdown
                time.sleep(2)
                
                # Check if process still exists
                try:
                    os.kill(pid, 0)  # Check if process exists
                    # If we reach here, process is still running, force kill
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    # Process already terminated
                    pass
                    
            except ProcessLookupError:
                # Process doesn't exist
                pass
        
        # Cleanup container resources
        self._cleanup_container(container_id, container_config)
        
        # Update status
        container_config['status'] = 'exited'
        container_config['stopped'] = datetime.now().isoformat()
        container_config['pid'] = None
        self._save_container_config(container_id, container_config)
        
        if container_id in self.running_containers:
            del self.running_containers[container_id]
        
        print(f"Container {container_id} stopped")
    
    def remove_container(self, container_id, force=False):
        """Remove a container"""
        container_config = self._load_container_config(container_id)
        
        if container_config['status'] == 'running' and not force:
            raise ValueError(f"Cannot remove running container {container_id}. Stop it first or use --force")
        
        if container_config['status'] == 'running':
            self.stop_container(container_id)
        
        # Remove container files
        container_file = self.containers_dir / f"{container_id}.json"
        if container_file.exists():
            container_file.unlink()
        
        # Remove container filesystem
        container_dir = self.storage_path / "containers" / container_id
        if container_dir.exists():
            import shutil
            shutil.rmtree(container_dir)
        
        print(f"Container {container_id} removed")
    
    def list_containers(self, all_containers=False):
        """List containers"""
        containers = []
        
        for container_file in self.containers_dir.glob("*.json"):
            with open(container_file, 'r') as f:
                config = json.load(f)
            
            if not all_containers and config['status'] not in ['running', 'starting']:
                continue
            
            containers.append({
                'id': config['id'],
                'image': config['image'],
                'command': ' '.join(config['command']),
                'status': config['status'],
                'created': config['created'][:19].replace('T', ' ')
            })
        
        return containers
    
    def exec_container(self, container_id, command, interactive=False):
        """Execute command in running container"""
        container_config = self._load_container_config(container_id)
        
        if container_config['status'] != 'running':
            raise ValueError(f"Container {container_id} is not running")
        
        pid = container_config.get('pid')
        if not pid:
            raise ValueError(f"Container {container_id} has no associated process")
        
        # Use nsenter to enter container namespaces
        nsenter_cmd = [
            'nsenter', 
            '--target', str(pid),
            '--mount', '--uts', '--ipc', '--net', '--pid',
            '--'
        ] + command
        
        try:
            if interactive:
                subprocess.run(nsenter_cmd)
            else:
                result = subprocess.run(nsenter_cmd, capture_output=True, text=True)
                print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}")
    
    def _setup_container(self, container_id, config):
        """Setup container environment"""
        # Get image path
        image_path = self.storage_path / "images" / config['image'].replace(':', '_')
        
        # Setup container filesystem
        fs_info = setup_container_rootfs(image_path, container_id, self.storage_path)
        
        # Create cgroup for resource limits
        cgroup_path = self.cgroup_manager.create_container_cgroup(
            container_id, 
            config.get('cpu_limit'),
            config.get('memory_limit')
        )
        
        # Setup network namespace
        network_ns = create_network_namespace(container_id)
        config['network_namespace'] = network_ns
        
        # Setup volume mounts
        mount_points = []
        rootfs = fs_info['merged']
        
        for volume in config.get('volumes', []):
            if ':' in volume:
                host_path, container_path = volume.split(':', 1)
                target_path = Path(rootfs) / container_path.lstrip('/')
                
                if bind_mount(host_path, target_path):
                    mount_points.append(str(target_path))
        
        # Store setup info
        config['_fs_info'] = fs_info
        config['_cgroup_path'] = cgroup_path
        config['_mount_points'] = mount_points
    
    def _start_container_process(self, container_id, config):
        """Start container process in background"""
        # Fork process
        pid = os.fork()
        
        if pid == 0:
            # Child process - setup container and exec
            try:
                self._execute_in_container(container_id, config)
            except Exception as e:
                print(f"Failed to start container: {e}")
                os._exit(1)
        else:
            # Parent process
            return pid
    
    def _run_container_process(self, container_id, config):
        """Run container process in foreground"""
        self._execute_in_container(container_id, config)
    
    def _execute_in_container(self, container_id, config):
        """Execute command inside container with proper isolation"""
        # Setup container environment (namespaces, hostname, etc.)
        setup_container_environment(container_id)
        
        # Change to container rootfs
        rootfs = config['_fs_info']['merged']
        os.chroot(rootfs)
        os.chdir(config.get('working_dir', '/'))
        
        # Set environment variables
        for env_var in config.get('environment', []):
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                os.environ[key] = value
        
        # Add process to cgroup
        if config.get('_cgroup_path'):
            self.cgroup_manager.add_process_to_cgroup(config['_cgroup_path'], os.getpid())
        
        # Execute the command
        try:
            os.execvp(config['command'][0], config['command'])
        except FileNotFoundError:
            print(f"Command not found: {config['command'][0]}")
            os._exit(127)
    
    def _cleanup_container(self, container_id, config):
        """Cleanup container resources"""
        # Cleanup mount points
        if '_mount_points' in config:
            cleanup_mounts(config['_mount_points'])
        
        # Cleanup filesystem
        if '_fs_info' in config:
            fs_info = config['_fs_info']
            if 'merged' in fs_info:
                unmount_overlay(fs_info['merged'])
        
        # Cleanup cgroup
        if '_cgroup_path' in config:
            self.cgroup_manager.remove_container_cgroup(container_id)
        
        # Cleanup network namespace
        if config.get('network_namespace'):
            cleanup_network_namespace(config['network_namespace'])
    
    def _load_container_config(self, container_id):
        """Load container configuration"""
        container_file = self.containers_dir / f"{container_id}.json"
        
        if not container_file.exists():
            raise FileNotFoundError(f"Container {container_id} not found")
        
        with open(container_file, 'r') as f:
            return json.load(f)
    
    def _save_container_config(self, container_id, config):
        """Save container configuration"""
        container_file = self.containers_dir / f"{container_id}.json"
        
        with open(container_file, 'w') as f:
            json.dump(config, f, indent=2)