#!/bin/bash
source ~/.profile

# Convert the ROS1 params file to a valid ROS2 params file
echo "bridge_server_ros2:" >> /ros2_params.yaml
echo "  ros__parameters:" >> /ros2_params.yaml
sed 's/^/       /' /ros_params.yaml >> /ros2_params.yaml

ros2 run ros2_bridge_grpc bridge_server_ros2 --ros-args --params-file /ros2_params.yaml