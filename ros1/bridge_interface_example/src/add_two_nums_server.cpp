#include "ros/init.h"
#include "ros/node_handle.h"
#include "ros/service_server.h"
#include <ros/ros.h>
#include <bridge_interface_example/add_two_nums.h>

bool addNums(bridge_interface_example::add_two_nums::Request& req, bridge_interface_example::add_two_nums::Response& resp) {
    ROS_INFO("Get a request to add %.2f and %.2f", req.num1, req.num2);
    resp.result.operand_1 = req.num1;
    resp.result.operand_2 = req.num2;
    resp.result.result = req.num1 + req.num2;
    return true;
}

int main(int argc, char* argv[]) {
    ros::init(argc, argv, "add_two_nums_service");

    ros::NodeHandle nh;
    ros::ServiceServer service = nh.advertiseService("/add_two_nums", addNums);
    ROS_INFO("/add_two_nums service online");

    ros::spin();
    ros::shutdown();
    return 0;
}