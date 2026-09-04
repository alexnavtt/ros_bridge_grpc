cmake_minimum_required(VERSION 3.8)
project(ros2_bridge_grpc)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)
find_package(utf8_range REQUIRED)

string(STRIP "$ENV{MESSAGE_PACKAGES}" PACKAGE_LIST_STRING)
separate_arguments(PACKAGE_LIST UNIX_COMMAND "${PACKAGE_LIST_STRING}")
message("PACKAGE LIST = ${PACKAGE_LIST}")
foreach(pkg IN LISTS PACKAGE_LIST)
    find_package(${pkg} REQUIRED)
    list(APPEND LIBRARY_LIST "${pkg}::${pkg}")
endforeach()

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
target_link_libraries(bridge_server_ros2 
    rclcpp::rclcpp
    gRPC::grpc++ 
    conversions
)

target_link_libraries(conversions
    rclcpp::rclcpp
    ${LIBRARY_LIST}
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
