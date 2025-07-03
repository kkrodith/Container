#!/usr/bin/env python3
"""
MyDocker - A Mini Docker Clone
Main CLI interface providing Docker-like commands
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.container import ContainerManager
from core.image import ImageManager
from core.registry import RegistryManager
from core.builder import ImageBuilder
from utils.namespace import check_privileges

class MyDocker:
    def __init__(self):
        self.container_manager = ContainerManager()
        self.image_manager = ImageManager()
        self.registry_manager = RegistryManager()
        self.builder = ImageBuilder()
        
    def run(self, args):
        """Run a new container"""
        print(f"Running container from image: {args.image}")
        
        # Pull image if not available locally
        if not self.image_manager.image_exists(args.image):
            print(f"Image {args.image} not found locally, pulling...")
            self.registry_manager.pull_image(args.image)
        
        # Create and start container
        container_id = self.container_manager.create_container(
            image=args.image,
            command=args.command,
            interactive=args.interactive,
            volumes=args.volume,
            environment=args.env,
            working_dir=args.workdir
        )
        
        print(f"Container ID: {container_id}")
        
        if args.detach:
            self.container_manager.start_container(container_id)
        else:
            self.container_manager.run_container(container_id)
    
    def pull(self, args):
        """Pull an image from registry"""
        print(f"Pulling image: {args.image}")
        self.registry_manager.pull_image(args.image)
        print(f"Successfully pulled {args.image}")
    
    def build(self, args):
        """Build an image from Dockerfile"""
        print(f"Building image: {args.tag}")
        image_id = self.builder.build_image(
            dockerfile_path=args.dockerfile,
            context_path=args.path,
            tag=args.tag
        )
        print(f"Successfully built image: {image_id}")
    
    def ps(self, args):
        """List containers"""
        containers = self.container_manager.list_containers(all_containers=args.all)
        
        print(f"{'CONTAINER ID':<12} {'IMAGE':<20} {'COMMAND':<20} {'STATUS':<15} {'CREATED':<15}")
        print("-" * 82)
        
        for container in containers:
            print(f"{container['id']:<12} {container['image']:<20} {container['command']:<20} "
                  f"{container['status']:<15} {container['created']:<15}")
    
    def stop(self, args):
        """Stop a container"""
        for container_id in args.containers:
            print(f"Stopping container: {container_id}")
            self.container_manager.stop_container(container_id)
    
    def start(self, args):
        """Start a container"""
        for container_id in args.containers:
            print(f"Starting container: {container_id}")
            self.container_manager.start_container(container_id)
    
    def rm(self, args):
        """Remove containers"""
        for container_id in args.containers:
            print(f"Removing container: {container_id}")
            self.container_manager.remove_container(container_id, force=args.force)
    
    def images(self, args):
        """List images"""
        images = self.image_manager.list_images()
        
        print(f"{'REPOSITORY':<20} {'TAG':<10} {'IMAGE ID':<12} {'CREATED':<15} {'SIZE':<10}")
        print("-" * 67)
        
        for image in images:
            print(f"{image['repository']:<20} {image['tag']:<10} {image['id']:<12} "
                  f"{image['created']:<15} {image['size']:<10}")
    
    def rmi(self, args):
        """Remove images"""
        for image in args.images:
            print(f"Removing image: {image}")
            self.image_manager.remove_image(image, force=args.force)
    
    def exec(self, args):
        """Execute command in running container"""
        print(f"Executing '{' '.join(args.command)}' in container {args.container}")
        self.container_manager.exec_container(
            container_id=args.container,
            command=args.command,
            interactive=args.interactive
        )

def create_parser():
    """Create the argument parser"""
    parser = argparse.ArgumentParser(description='MyDocker - A Mini Docker Clone')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # run command
    run_parser = subparsers.add_parser('run', help='Run a command in a new container')
    run_parser.add_argument('image', help='Container image')
    run_parser.add_argument('command', nargs='*', default=['/bin/sh'], help='Command to run')
    run_parser.add_argument('-i', '--interactive', action='store_true', help='Keep STDIN open')
    run_parser.add_argument('-t', '--tty', action='store_true', help='Allocate a pseudo-TTY')
    run_parser.add_argument('-d', '--detach', action='store_true', help='Run container in background')
    run_parser.add_argument('-v', '--volume', action='append', help='Bind mount a volume')
    run_parser.add_argument('-e', '--env', action='append', help='Set environment variables')
    run_parser.add_argument('-w', '--workdir', help='Working directory inside container')
    
    # pull command
    pull_parser = subparsers.add_parser('pull', help='Pull an image from a registry')
    pull_parser.add_argument('image', help='Image to pull')
    
    # build command
    build_parser = subparsers.add_parser('build', help='Build an image from a Dockerfile')
    build_parser.add_argument('path', default='.', nargs='?', help='Build context path')
    build_parser.add_argument('-t', '--tag', required=True, help='Name and optionally tag')
    build_parser.add_argument('-f', '--dockerfile', default='Dockerfile', help='Name of the Dockerfile')
    
    # ps command
    ps_parser = subparsers.add_parser('ps', help='List containers')
    ps_parser.add_argument('-a', '--all', action='store_true', help='Show all containers')
    
    # stop command
    stop_parser = subparsers.add_parser('stop', help='Stop one or more running containers')
    stop_parser.add_argument('containers', nargs='+', help='Container IDs to stop')
    
    # start command
    start_parser = subparsers.add_parser('start', help='Start one or more stopped containers')
    start_parser.add_argument('containers', nargs='+', help='Container IDs to start')
    
    # rm command
    rm_parser = subparsers.add_parser('rm', help='Remove one or more containers')
    rm_parser.add_argument('containers', nargs='+', help='Container IDs to remove')
    rm_parser.add_argument('-f', '--force', action='store_true', help='Force removal')
    
    # images command
    images_parser = subparsers.add_parser('images', help='List images')
    
    # rmi command
    rmi_parser = subparsers.add_parser('rmi', help='Remove one or more images')
    rmi_parser.add_argument('images', nargs='+', help='Image IDs to remove')
    rmi_parser.add_argument('-f', '--force', action='store_true', help='Force removal')
    
    # exec command
    exec_parser = subparsers.add_parser('exec', help='Run a command in a running container')
    exec_parser.add_argument('container', help='Container ID')
    exec_parser.add_argument('command', nargs='+', help='Command to execute')
    exec_parser.add_argument('-i', '--interactive', action='store_true', help='Keep STDIN open')
    
    return parser

def main():
    # Check if running with sufficient privileges
    if not check_privileges():
        print("Error: MyDocker requires root privileges to create namespaces")
        print("Please run with sudo: sudo ./mydocker.py")
        sys.exit(1)
    
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Initialize MyDocker
    mydocker = MyDocker()
    
    # Route to appropriate handler
    try:
        handler = getattr(mydocker, args.command)
        handler(args)
    except AttributeError:
        print(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()