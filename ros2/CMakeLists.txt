cmake_minimum_required(VERSION 3.8)
project(ros2_bridge_grpc)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(Protobuf REQUIRED PATHS /home/alex/.local/src/grpc/install/lib/cmake/protobuf NO_DEFAULT_PATH)
find_package(gRPC REQUIRED)

find_package(action_msgs REQUIRED)
find_package(action_tutorials_interfaces REQUIRED)
find_package(actionlib_msgs REQUIRED)
find_package(apriltag_msgs REQUIRED)
find_package(bond REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(composition_interfaces REQUIRED)
find_package(control_msgs REQUIRED)
find_package(controller_manager_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(dwb_msgs REQUIRED)
find_package(example_interfaces REQUIRED)
find_package(gazebo_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(logging_demo REQUIRED)
find_package(map_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(nav_2d_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(object_recognition_msgs REQUIRED)
find_package(octomap_msgs REQUIRED)
find_package(pcl_msgs REQUIRED)
find_package(pendulum_msgs REQUIRED)
find_package(rcl_interfaces REQUIRED)
find_package(realsense2_camera_msgs REQUIRED)
find_package(rmw_dds_common REQUIRED)
find_package(rosbag2_interfaces REQUIRED)
find_package(rosgraph_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(slam_toolbox REQUIRED)
find_package(statistics_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(stereo_msgs REQUIRED)
find_package(teleop_tools_msgs REQUIRED)
find_package(tf2_msgs REQUIRED)
find_package(topic_tools_interfaces REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(turtlesim REQUIRED)
find_package(twist_mux_msgs REQUIRED)
find_package(unique_identifier_msgs REQUIRED)
find_package(velodyne_msgs REQUIRED)
find_package(visualization_msgs REQUIRED)

include_directories(
    /home/alex/workspaces/project_ws/src/ros1_bridge_grpc/generated/conversions
    /home/alex/workspaces/project_ws/src/ros1_bridge_grpc/generated/grpc_cpp
    /home/alex/workspaces/project_ws/src/ros1_bridge_grpc/generated/proto_cpp
    /home/alex/workspaces/project_ws/src/ros1_bridge_grpc/common
    ${Protobuf_INCLUDE_DIRS}
)

add_compile_definitions(ROS2)

file(GLOB CONVERSION_SOURCES "/home/alex/workspaces/project_ws/src/ros1_bridge_grpc/generated/conversions/ros2/*.cpp")
add_library(conversions SHARED ${CONVERSION_SOURCES})
target_link_libraries(conversions gRPC::grpc++)

add_executable(bridge_server_ros2 bridge_server_ros2.cpp)
ament_target_dependencies(bridge_server_ros2 rclcpp)
target_link_libraries(bridge_server_ros2 gRPC::grpc++ conversions)

ament_target_dependencies(conversions
    action_msgs
    action_tutorials_interfaces
    actionlib_msgs
    apriltag_msgs
    bond
    builtin_interfaces
    composition_interfaces
    control_msgs
    controller_manager_msgs
    diagnostic_msgs
    dwb_msgs
    example_interfaces
    gazebo_msgs
    geometry_msgs
    lifecycle_msgs
    logging_demo
    map_msgs
    moveit_msgs
    nav2_msgs
    nav_2d_msgs
    nav_msgs
    object_recognition_msgs
    octomap_msgs
    pcl_msgs
    pendulum_msgs
    rcl_interfaces
    realsense2_camera_msgs
    rmw_dds_common
    rosbag2_interfaces
    rosgraph_msgs
    sensor_msgs
    shape_msgs
    slam_toolbox
    statistics_msgs
    std_msgs
    std_srvs
    stereo_msgs
    teleop_tools_msgs
    tf2_msgs
    topic_tools_interfaces
    trajectory_msgs
    turtlesim
    twist_mux_msgs
    unique_identifier_msgs
    velodyne_msgs
    visualization_msgs
)
