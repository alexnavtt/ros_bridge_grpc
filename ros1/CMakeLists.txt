cmake_minimum_required(VERSION 3.8)
project(ros1_bridge_grpc)

set(CMAKE_CXX_STANDARD 17)

string(STRIP "$ENV{MESSAGE_PACKAGES}" PACKAGE_LIST_STRING)
separate_arguments(PACKAGE_LIST UNIX_COMMAND "${PACKAGE_LIST_STRING}")
message("PACKAGE LIST = ${PACKAGE_LIST}")
foreach(pkg IN LISTS PACKAGE_LIST)
    find_package(${pkg} REQUIRED)
endforeach()

find_package(Protobuf REQUIRED)
find_package(gRPC REQUIRED)
find_package(utf8_range REQUIRED)
find_package(catkin REQUIRED COMPONENTS 
    roscpp
    ${PACKAGE_LIST}
)

catkin_package()

include_directories(
    ${catkin_INCLUDE_DIRS}
    /generated/conversions
    /generated/grpc_cpp
    /generated/proto_cpp
    /common
)

add_compile_definitions(ROS1)

file(GLOB CONVERSION_SOURCES "/generated/conversions/ros1/*.cpp")
file(GLOB GRPC_SOURCES "/generated/grpc_cpp/*.cc")
file(GLOB PROTO_SOURCES "/generated/proto_cpp/*.cc")
add_library(conversions SHARED ${CONVERSION_SOURCES} ${GRPC_SOURCES} ${PROTO_SOURCES} /common/custom_conversions.hpp)
target_link_libraries(conversions gRPC::grpc++ protobuf::libprotobuf utf8_range::utf8_validity ${catkin_LIBRARIES})

add_executable(bridge_server_ros1 bridge_server_ros1.cpp)
target_link_libraries(bridge_server_ros1 conversions gRPC::grpc++ ${catkin_LIBRARIES})
