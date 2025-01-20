cmake_minimum_required(VERSION 3.8)
project(ros1_bridge_grpc)

find_package(catkin REQUIRED COMPONENTS roscpp)
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)

include_directories(${catkin_INCLUDE_DIRS})

add_executable(bridge_server_ros1 bridge_server_ros1.cpp)
target_link_libraries(bridge_server_ros1 gRPC::grpc++ ${catkin_LIBRARIES})
