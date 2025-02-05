cmake_minimum_required(VERSION 3.8)
project(ros1_bridge_grpc)

set(CMAKE_CXX_STANDARD 17)

find_package(Protobuf REQUIRED PATHS /home/alex/.local/src/grpc/install/lib/cmake/protobuf)
find_package(gRPC REQUIRED)
find_package(catkin REQUIRED COMPONENTS 
    roscpp
    std_msgs
)

catkin_package()

include_directories(
    ${catkin_INCLUDE_DIRS}
    /home/alex/catkin_ws/src/ros1_bridge_grpc/generated/conversions
    /home/alex/catkin_ws/src/ros1_bridge_grpc/generated/grpc_cpp
    /home/alex/catkin_ws/src/ros1_bridge_grpc/generated/proto_cpp
    /home/alex/catkin_ws/src/ros1_bridge_grpc/common
    ${Protobuf_INCLUDE_DIRS}
)

add_compile_definitions(ROS1)

file(GLOB CONVERSION_SOURCES "${CMAKE_SOURCE_DIR}/../generated/conversions/ros1/*.cpp")
file(GLOB GRPC_SOURCES "${CMAKE_SOURCE_DIR}/../generated/grpc_cpp/*.cc")
file(GLOB PROTO_SOURCES "${CMAKE_SOURCE_DIR}/../generated/proto_cpp/*.cc")
add_library(conversions SHARED ${CONVERSION_SOURCES} ${GRPC_SOURCES} ${PROTO_SOURCES} ${CMAKE_SOURCE_DIR}/../common/custom_conversions.hpp)
target_link_libraries(conversions gRPC::grpc++ ${Protobuf_LIBRARIES} ${catkin_LIBRARIES})

add_executable(bridge_server_ros1 bridge_server_ros1.cpp)
target_link_libraries(bridge_server_ros1 conversions gRPC::grpc++ ${catkin_LIBRARIES})
