cmake_minimum_required(VERSION 3.8)
project(ros2_bridge_grpc)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)
find_package(utf8_range REQUIRED)

find_package(std_msgs REQUIRED)

include_directories(
    /generated/conversions
    /generated/grpc_cpp
    /generated/proto_cpp
    /common
)

add_compile_definitions(ROS2)

file(GLOB CONVERSION_SOURCES "/generated/conversions/ros2/*.cpp")
file(GLOB GRPC_SOURCES "/generated/grpc_cpp/*.cc")
file(GLOB PROTO_SOURCES "/generated/proto_cpp/*.cc")
add_library(conversions SHARED ${CONVERSION_SOURCES} ${GRPC_SOURCES} ${PROTO_SOURCES} /common/custom_conversions.hpp)
target_link_libraries(conversions 
    gRPC::grpc++
    protobuf::libprotobuf
    utf8_range::utf8_validity
)

add_executable(bridge_server_ros2 bridge_server_ros2.cpp)
ament_target_dependencies(bridge_server_ros2 rclcpp)
target_link_libraries(bridge_server_ros2 gRPC::grpc++ conversions)

ament_target_dependencies(conversions
    rclcpp
    std_msgs
)

install(TARGETS
    bridge_server_ros2
    DESTINATION lib/${PROJECT_NAME}
)

install(TARGETS
    conversions
    DESTINATION lib
)

ament_package()
