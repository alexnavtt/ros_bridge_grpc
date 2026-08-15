#!/usr/bin/bash

# Make sure to run from the docker folder
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Make sure these folders exist
mkdir -p mapped/ros1
mkdir -p mapped/ros2

eval "$(python3 ../scripts/set_env_params.py $ROS_BRIDGE_BUILD_CONFIG)"
docker compose --profile all build

# If the build was successful, copy the generated folder out
if [ $? -eq 0 ]; then
    docker compose up -d ros1_bridge_introspection
    sudo rm -rf ./../generated
    docker cp ros1_bridge_${ROS_BRIDGE_GRPC_ROS1_DISTRO}_introspection:/generated/ ./../generated
    sudo chown -R $(whoami):$(whoami) ./../generated
    docker compose down ros1_bridge_introspection
fi

for file in ../docker/mapped/ros1/*; do
    (sudo umount "$file") || true;
    rmdir $file
done

for file in ../docker/mapped/ros2/*; do
    (sudo umount $file) || true;
    rmdir $file
done