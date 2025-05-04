#!/bin/bash
source ~/.profile
ros2 run ros2_bridge_grpc bridge_server_ros2 --ros-args --params-file /ros_params.yaml