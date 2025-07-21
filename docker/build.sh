#!/usr/bin/bash

# Make sure these folders exist
mkdir -p mapped/ros1
mkdir -p mapped/ros2

eval "$(sudo -E python3 ../scripts/set_env_params.py $ROS_BRIDGE_BUILD_CONFIG)"
docker compose --profile all build

for file in ../docker/mapped/ros1/*; do
    (sudo umount "$file") || true;
    rmdir $file
done

for file in ../docker/mapped/ros2/*; do
    (sudo umount $file) || true;
    rmdir $file
done