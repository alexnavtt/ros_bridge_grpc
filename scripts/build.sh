#!/usr/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root. Use sudo -E." >&2
  exit 1
fi

eval "$(python3 set_env_params.py $1)"
cd ../docker
docker compose build

for file in ../docker/mapped/ros1/*; do
    (umount "$file") || true;
    rmdir $file
done

for file in ../docker/mapped/ros2/*; do
    (umount $file) || true;
    rmdir $file
done