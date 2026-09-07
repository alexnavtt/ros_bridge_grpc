#!/usr/bin/bash

# Make sure to run from the docker folder
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

eval "$(python3 ../scripts/set_env_params.py $ROS_BRIDGE_BUILD_CONFIG)"

if [ -z "$(docker image ls | grep grpc_bridge_base:${ROS_BRIDGE_GRPC_SIDE_A_UBUNTU})" ]; then
    UBUNTU_DISTRO=$ROS_BRIDGE_GRPC_SIDE_A_UBUNTU docker compose build grpc_base
fi

if [ $? -ne 0 ]; then return 1; fi
if [ -z "$(docker image ls | grep grpc_bridge_base:${ROS_BRIDGE_GRPC_SIDE_B_UBUNTU})" ]; then
    UBUNTU_DISTRO=$ROS_BRIDGE_GRPC_SIDE_B_UBUNTU docker compose build grpc_base
fi

if [ $? -ne 0 ]; then return 1; fi
docker compose build side_a_introspection

# If the build was successful, copy the generated proto definitions out
if [ $? -eq 0 ]; then
    docker compose up -d side_a_introspection
    sudo rm -rf ./../generated
    mkdir ./../generated
    docker cp ros_bridge_${ROS_BRIDGE_GRPC_SIDE_A_DISTRO}_${ROS_BRIDGE_GRPC_SIDE_B_DISTRO}_introspection_A:/generated/proto ./../generated/proto_A
    sudo chown -R $(whoami):$(whoami) ./../generated
    docker compose down side_a_introspection
fi

if [ "$ROS_BRIDGE_GRPC_SIDE_A_DISTRO" != "$ROS_BRIDGE_GRPC_SIDE_B_DISTRO" ]; then
    docker compose build side_b_introspection

    # If the build was successful, copy the generated folder out
    if [ $? -eq 0 ]; then
        docker compose up -d side_b_introspection
        docker cp ros_bridge_${ROS_BRIDGE_GRPC_SIDE_A_DISTRO}_${ROS_BRIDGE_GRPC_SIDE_B_DISTRO}_introspection_B:/generated/ ./../generated/proto_B
        sudo chown -R $(whoami):$(whoami) ./../generated
        docker compose down side_b_introspection
    fi
fi

# Finish the build
printf "Building bridge for %s" $ROS_BRIDGE_GRPC_SIDE_A_DISTRO
docker compose build side_a_bridge

if [ $? -eq 0 ]; then
    docker compose up -d side_a_bridge_dev
    docker cp side_a_bridge_dev:/generated/ ./../generated/final
    sudo chown -R $(whoami):$(whoami) ./../generated
    docker compose down side_a_bridge_dev
fi

if [ "$ROS_BRIDGE_GRPC_SIDE_A_DISTRO" != "$ROS_BRIDGE_GRPC_SIDE_B_DISTRO" ]; then
    printf "Building bridge for %s" $ROS_BRIDGE_GRPC_SIDE_B_DISTRO
    docker compose build side_b_bridge
fi

if [ ! -z "$(ls -A ../docker/mapped/side_B)" ]; then
    for file in ../docker/mapped/side_B/*; do
        sudo umount -f "$file"
        rmdir $file
    done
fi

if [ ! -z "$(ls -A ../docker/mapped/side_A)" ]; then
    for file in ../docker/mapped/side_A/*; do
        sudo umount -f $file
        rmdir $file
    done
fi

echo "ROS Bridge Build Complete"
