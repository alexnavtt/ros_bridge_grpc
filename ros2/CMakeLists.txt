cmake_minimum_required(VERSION 3.8)
project(ros2_bridge_server)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)

add_executable(bridge_server_ros2 bridge_server_ros2.cpp)
ament_target_dependencies(bridge_server_ros2 rclcpp gRPC)
target_link_libraries(bridge_server_ros2 gRPC::grpc++)
