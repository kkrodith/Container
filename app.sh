#!/bin/bash

echo "Welcome to MyDocker!"
echo "This is a demo application running in a container"
echo "Current directory: $(pwd)"
echo "Environment variables:"
env | grep APP
echo "Container hostname: $(hostname)"
echo "Process ID: $$"