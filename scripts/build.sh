#!/usr/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root. Use sudo -E." >&2
  exit 1
fi

eval "$(python3 set_env_params.py $1)"
echo "USER REPOS: " $ROS_BRIDGE_GRPC_USER_REPOS
cd ../docker
docker compose build

for file in ../docker/mapped/*; do
    [ "$(basename "$file")" = ".gitkeep" ] && continue  # Skip .gitkeep
    sudo umount $file
done