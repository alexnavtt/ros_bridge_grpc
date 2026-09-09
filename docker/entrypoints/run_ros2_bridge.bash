#!/bin/bash
source ~/.profile

# Convert the ROS1 params file to a valid ROS2 params file
rm -f /ros2_params.yaml
echo "bridge_server_ros2:" >> /ros2_params.yaml
echo "  ros__parameters:" >> /ros2_params.yaml
sed 's/^/       /' /ros_params.yaml >> /ros2_params.yaml

# Reconcile changes to FastRTPS
if [[ "${ROS_DISTRO}" =~ ^[l-z] ]]; then
    export FASTDDS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE
    unset FASTRTPS_DEFAULT_PROFILES_FILE
fi

ros2 run ros2_bridge_grpc bridge_server_ros2 --ros-args --params-file /ros2_params.yaml