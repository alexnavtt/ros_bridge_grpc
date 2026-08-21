#include <rclcpp/rclcpp.hpp>
#include <bridge_interface_example/srv/add_two_nums.hpp>

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    auto node = std::make_shared<rclcpp::Node>("add_two_nums_service");

    auto addNums = [node](
        const bridge_interface_example::srv::AddTwoNums::Request::SharedPtr req, 
        bridge_interface_example::srv::AddTwoNums::Response::SharedPtr resp) 
    {
        RCLCPP_INFO(node->get_logger(), "Get a request to add %.2f and %.2f", req->num1, req->num2);
        resp->result.operand_1 = req->num1;
        resp->result.operand_2 = req->num2;

        // Just a cautionary note
        // Just because a service exists on both sides of the bridge
        // doesn't mean it's doing the same thing on each side
        resp->result.result = req->num1 + req->num2 + 0.5;
        return true;
    };

    auto service = node->create_service<bridge_interface_example::srv::AddTwoNums>("/add_two_nums", addNums);
    RCLCPP_INFO(node->get_logger(), "/add_two_nums service online");

    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}