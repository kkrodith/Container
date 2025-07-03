"""
Cgroup utilities for resource management
"""

import os
import subprocess
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")
MYDOCKER_CGROUP = "mydocker"

class CgroupManager:
    def __init__(self):
        self.cgroup_root = CGROUP_ROOT
        self.mydocker_root = self.cgroup_root / MYDOCKER_CGROUP
        self._ensure_mydocker_cgroup()
    
    def _ensure_mydocker_cgroup(self):
        """Ensure mydocker cgroup exists"""
        try:
            if not self.mydocker_root.exists():
                self.mydocker_root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            print("Warning: Cannot create cgroup, resource limits will not work")
    
    def create_container_cgroup(self, container_id, cpu_limit=None, memory_limit=None):
        """
        Create cgroup for container with resource limits
        
        Args:
            container_id: Container identifier
            cpu_limit: CPU limit (e.g., "0.5" for 50% of one CPU)
            memory_limit: Memory limit (e.g., "512m", "1g")
        """
        cgroup_path = self.mydocker_root / container_id
        
        try:
            cgroup_path.mkdir(exist_ok=True)
            
            # Set CPU limits
            if cpu_limit:
                self._set_cpu_limit(cgroup_path, cpu_limit)
            
            # Set memory limits
            if memory_limit:
                self._set_memory_limit(cgroup_path, memory_limit)
            
            return str(cgroup_path)
            
        except (PermissionError, FileNotFoundError) as e:
            print(f"Warning: Failed to create cgroup: {e}")
            return None
    
    def _set_cpu_limit(self, cgroup_path, cpu_limit):
        """Set CPU limit for cgroup"""
        try:
            # Convert CPU limit to quota and period
            cpu_quota = int(float(cpu_limit) * 100000)  # 100ms period
            cpu_period = 100000
            
            # Write CPU limits
            (cgroup_path / "cpu.cfs_quota_us").write_text(str(cpu_quota))
            (cgroup_path / "cpu.cfs_period_us").write_text(str(cpu_period))
            
        except (ValueError, FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to set CPU limit: {e}")
    
    def _set_memory_limit(self, cgroup_path, memory_limit):
        """Set memory limit for cgroup"""
        try:
            # Parse memory limit
            memory_bytes = self._parse_memory_limit(memory_limit)
            
            # Write memory limit
            memory_file = cgroup_path / "memory.limit_in_bytes"
            if memory_file.exists():
                memory_file.write_text(str(memory_bytes))
            else:
                # Try cgroup v2 format
                memory_file = cgroup_path / "memory.max"
                if memory_file.exists():
                    memory_file.write_text(str(memory_bytes))
            
        except (ValueError, FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to set memory limit: {e}")
    
    def _parse_memory_limit(self, memory_limit):
        """Parse memory limit string to bytes"""
        memory_limit = memory_limit.lower().strip()
        
        if memory_limit.endswith('k'):
            return int(memory_limit[:-1]) * 1024
        elif memory_limit.endswith('m'):
            return int(memory_limit[:-1]) * 1024 * 1024
        elif memory_limit.endswith('g'):
            return int(memory_limit[:-1]) * 1024 * 1024 * 1024
        else:
            return int(memory_limit)
    
    def add_process_to_cgroup(self, cgroup_path, pid):
        """Add process to cgroup"""
        try:
            cgroup = Path(cgroup_path)
            
            # Add to cgroup.procs (cgroup v2) or tasks (cgroup v1)
            procs_file = cgroup / "cgroup.procs"
            if procs_file.exists():
                procs_file.write_text(str(pid))
            else:
                tasks_file = cgroup / "tasks"
                if tasks_file.exists():
                    tasks_file.write_text(str(pid))
            
        except (FileNotFoundError, PermissionError) as e:
            print(f"Warning: Failed to add process to cgroup: {e}")
    
    def remove_container_cgroup(self, container_id):
        """Remove container cgroup"""
        cgroup_path = self.mydocker_root / container_id
        
        try:
            if cgroup_path.exists():
                # Kill all processes in cgroup first
                self._kill_cgroup_processes(cgroup_path)
                
                # Remove cgroup directory
                cgroup_path.rmdir()
                
        except (PermissionError, OSError) as e:
            print(f"Warning: Failed to remove cgroup: {e}")
    
    def _kill_cgroup_processes(self, cgroup_path):
        """Kill all processes in a cgroup"""
        try:
            # Read process list
            procs_file = cgroup_path / "cgroup.procs"
            if procs_file.exists():
                pids = procs_file.read_text().strip().split('\n')
            else:
                tasks_file = cgroup_path / "tasks"
                if tasks_file.exists():
                    pids = tasks_file.read_text().strip().split('\n')
                else:
                    return
            
            # Kill each process
            for pid in pids:
                if pid.strip():
                    try:
                        subprocess.run(['kill', '-TERM', pid.strip()], 
                                     stderr=subprocess.DEVNULL)
                    except subprocess.CalledProcessError:
                        pass
            
            # Wait a bit, then force kill
            import time
            time.sleep(1)
            
            for pid in pids:
                if pid.strip():
                    try:
                        subprocess.run(['kill', '-KILL', pid.strip()], 
                                     stderr=subprocess.DEVNULL)
                    except subprocess.CalledProcessError:
                        pass
                        
        except (FileNotFoundError, PermissionError):
            pass
    
    def get_cgroup_stats(self, container_id):
        """Get resource usage statistics for container"""
        cgroup_path = self.mydocker_root / container_id
        stats = {}
        
        try:
            # CPU stats
            cpu_stat_file = cgroup_path / "cpuacct.stat"
            if cpu_stat_file.exists():
                cpu_stats = cpu_stat_file.read_text()
                for line in cpu_stats.split('\n'):
                    if line.strip():
                        key, value = line.split()
                        stats[f"cpu_{key}"] = int(value)
            
            # Memory stats
            memory_stat_file = cgroup_path / "memory.usage_in_bytes"
            if memory_stat_file.exists():
                stats["memory_usage"] = int(memory_stat_file.read_text().strip())
            
            memory_limit_file = cgroup_path / "memory.limit_in_bytes"
            if memory_limit_file.exists():
                stats["memory_limit"] = int(memory_limit_file.read_text().strip())
        
        except (FileNotFoundError, ValueError, PermissionError):
            pass
        
        return stats

def check_cgroup_support():
    """Check if cgroups are available"""
    return CGROUP_ROOT.exists()

def mount_cgroups():
    """Mount cgroup filesystem if not already mounted"""
    if not CGROUP_ROOT.exists():
        try:
            CGROUP_ROOT.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                'mount', '-t', 'cgroup', '-o', 'cpu,memory,cpuacct', 
                'cgroup', str(CGROUP_ROOT)
            ], check=True)
        except (subprocess.CalledProcessError, PermissionError):
            print("Warning: Failed to mount cgroups")