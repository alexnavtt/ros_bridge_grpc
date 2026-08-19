cmake_minimum_required(VERSION 3.8)
project(bridge_interface_example)

find_package(catkin REQUIRED COMPONENTS 
    roscpp
    message_generation
)

add_message_files(
    DIRECTORY msg
    FILES
    sum.msg
)

add_service_files(
    DIRECTORY srv
    FILES
    add_two_nums.srv
)

generate_messages()

include_directories(
    ${catkin_INCLUDE_DIRS}
)

catkin_package(
    CATKIN_DEPENDS message_runtime
)

add_executable(add_two_nums_client src/add_two_nums_client.cpp)
add_dependencies(add_two_nums_client
    ${${PROJECT_NAME}_EXPORTED_TARGETS}
    ${catkin_EXPORTED_TARGETS}
)
target_link_libraries(add_two_nums_client ${catkin_LIBRARIES})

add_executable(add_two_nums_server src/add_two_nums_server.cpp)
add_dependencies(add_two_nums_server
    ${${PROJECT_NAME}_EXPORTED_TARGETS}
    ${catkin_EXPORTED_TARGETS}
)
target_link_libraries(add_two_nums_server ${catkin_LIBRARIES})

install(
    DIRECTORY include/bridge_interface_example
    DESTINATION ${CATKIN_PACKAGE_INCLUDE_DESTINATION}
    PATTERN "*.h"
)
