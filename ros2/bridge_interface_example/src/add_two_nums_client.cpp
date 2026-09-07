#include <rclcpp/rclcpp.hpp>
#include <bridge_interface_example/srv/add_two_nums.hpp>

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    auto node = std::make_shared<rclcpp::Node>("add_two_nums_client");

    auto client = node->create_client<bridge_interface_example::srv::AddTwoNums>("/add_two_nums");
    if (!client->wait_for_service(std::chrono::seconds(5))) {
        RCLCPP_ERROR(node->get_logger(), "Could not contact the /add_two_nums service within 5 seconds");
        rclcpp::shutdown();
        exit(0);
    }
    RCLCPP_INFO(node->get_logger(), "Add Two Nums Client Online in ROS2");

    auto req = std::make_shared<bridge_interface_example::srv::AddTwoNums::Request>();
    req->num1 = 1;
    req->num2 = 2.72;

    auto resp_fut = client->async_send_request(req);
    auto ret_code = rclcpp::spin_until_future_complete(node, resp_fut, std::chrono::seconds(5));

    if (ret_code == rclcpp::FutureReturnCode::SUCCESS) {
        auto resp = resp_fut.get();
        RCLCPP_INFO(node->get_logger(), "Received a result! The sum of %.2f and %.2f is %.2f",
            resp->result.operand_1, resp->result.operand_2, resp->result.result);
    } else {
        RCLCPP_ERROR(node->get_logger(), "Failed to receive a response from the server within 5 seconds");
    }

    return 0;
}
