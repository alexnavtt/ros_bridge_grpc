cmake_minimum_required(VERSION 3.5)
project(bridge_interface_example)

set(CMAKE_CXX_STANDARD 14)

find_package(ament_cmake REQUIRED)

find_package(rclcpp REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_typesupport_cpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
    msg/Sum.msg
    srv/AddTwoNums.srv
)
ament_export_dependencies(rosidl_default_runtime)

add_executable(add_two_nums_client src/add_two_nums_client.cpp)
add_executable(add_two_nums_server src/add_two_nums_server.cpp)

if(COMMAND rosidl_get_typesupport_target)
    rosidl_get_typesupport_target(local_messages_cpp ${PROJECT_NAME} rosidl_typesupport_cpp)
    target_link_libraries(add_two_nums_client 
        ${local_messages_cpp}
        rclcpp::rclcpp
    )

    target_link_libraries(add_two_nums_server 
        ${local_messages_cpp}
        rclcpp::rclcpp
    )
else()
    target_link_libraries(add_two_nums_client rclcpp::rclcpp)
    rosidl_target_interfaces(add_two_nums_client ${PROJECT_NAME} "rosidl_typesupport_cpp")

    target_link_libraries(add_two_nums_server rclcpp::rclcpp)
    rosidl_target_interfaces(add_two_nums_server ${PROJECT_NAME} "rosidl_typesupport_cpp")
endif()

install(
    TARGETS
        add_two_nums_client
        add_two_nums_server
    DESTINATION
        lib/${PROJECT_NAME}
)

ament_package()
