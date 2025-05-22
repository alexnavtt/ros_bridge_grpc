#!/bin/bash
source ~/.profile

# Wait for roscore
echo "Waiting for ROS master..."
until rostopic list > /dev/null 2>&1; do
  sleep 1
done
echo "Connected to ROS master!"

rosparam load /ros_params.yaml 
rosrun ros1_bridge_grpc bridge_server_ros1