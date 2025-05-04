#!/bin/bash
source ~/.profile
roscore &
sleep 2
rosparam load /ros_params.yaml 
rosrun ros1_bridge_grpc bridge_server_ros1