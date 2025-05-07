#!/usr/bin/bash

eval "$(sudo -E python3 ../scripts/set_env_params.py $1)"
docker compose build

for file in ../docker/mapped/ros1/*; do
    (sudo umount "$file") || true;
    rmdir $file
done

for file in ../docker/mapped/ros2/*; do
    (sudo umount $file) || true;
    rmdir $file
done