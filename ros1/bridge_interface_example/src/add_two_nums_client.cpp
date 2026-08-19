#include <ros/ros.h>
#include <bridge_interface_example/add_two_nums.h>

int main(int argc, char* argv[]) {
    ros::init(argc, argv, "add_two_nums_client");
    
    ros::NodeHandle nh;

    ros::ServiceClient client = nh.serviceClient<bridge_interface_example::add_two_nums>("/add_two_nums");

    if (!ros::service::waitForService("/add_two_nums", ros::Duration(5))) {
        ROS_ERROR("Could not contact the /add_two_nums service within 5 seconds");
        ros::shutdown();
        exit(0);
    }
    ROS_INFO("Add Two Nums Client Online in ROS1");

    bridge_interface_example::add_two_nums srv_call;
    bridge_interface_example::add_two_nums::Request& req = srv_call.request;
    req.num1 = 2;
    req.num2 = 3.14;

    if (client.call(srv_call)) {
        ROS_INFO("Received a result! The sum of %.2f and %.2f is %.2f", 
            srv_call.response.result.operand_1, srv_call.response.result.operand_2, srv_call.response.result.result);
    } else {
        ROS_ERROR("Failed to receive a response from the server");
    }

    return 0;
}
