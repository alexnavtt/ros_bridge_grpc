#include <unordered_set>
#include <unordered_map>
#include <rclcpp/rclcpp.hpp>
#include <grpcpp/grpcpp.h>

class BridgeServerROS2 : public rclcpp::Node {
public:
    BridgeServerROS2(const std::string& name) : Node(name)
    {
        // Retrieve the list of topics and types for which to create bridges
        rcl_interfaces::msg::ParameterDescriptor registered_topics_config;
        registered_topics_config.name = "registered_topics";
        registered_topics_config.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING_ARRAY;
        registered_topics_config.description = "The list of topics and types to bridge in the form /my_namespace/my_topic:MyMessagePackage/MyMessageType";
        registered_topics_config.read_only = true;
        std::vector<std::string> registered_topics_param = declare_parameter(registered_topics_config.name, registered_topics_config);

        // Create a gRPC service builder to allow all types to register their callbacks with
        grpc::ServerBuilder builder;
        builder.AddListeningPort("127.0.0.1:50051", grpc::InsecureServerCredentials());

        // For each of them, register the corresponding communication elements
        for (const std::string& topic_name_and_type : registered_topics_param) {
            const std::size_t delim = topic_name_and_type.find(':');
            const std::string topic = topic_name_and_type.substr(0, delim);
            const std::string type  = topic_name_and_type.substr(delim+1); 

            if (!publisher_registration_callbacks.count(type) || !subscriber_registration_callbacks.count(type)) {
                RCLCPP_ERROR(get_logger(), "Requested type %s for topic %s is unknown to the bridge server, cannot make a connnection!", type.c_str(), topic.c_str());
                continue;
            }

            if (registered_topics_and_types.count(topic)) {
                if (registered_topics_and_types.at(topic) != type) {
                    RCLCPP_ERROR(get_logger(), "Failed to register topic %s using type %s as it clashes with an existing registration with type %s",
                        topic.c_str(), type.c_str(), registered_topics_and_types.at(topic).c_str());
                }
                continue;
            }

            registered_topics_and_types[topic] = type;
            publishers[topic] = publisher_registration_callbacks.at(type)(topic, *this, builder);
            subscribers[topic] = subscriber_registration_callbacks.at(type)(topic, *this);
        }

        // Finalize the gRPC server
        grpc_server = builder.BuildAndStart();
        grpc_server_thread = std::thread([this](){grpc_server->Wait();});
    }

    // The names of the topics we'd like to bridge and the types they're registered to
    std::unordered_map<std::string, std::string> registered_topics_and_types;

    // The publisher registration callbacks, which create a publisher to ROS2 and register a gRPC service
    using PublisherRegisterCallback_t = std::function<rclcpp::PublisherBase::SharedPtr(std::string, rclcpp::Node&, grpc::ServerBuilder&)>;
    static std::unordered_map<std::string, PublisherRegisterCallback_t> publisher_registration_callbacks;

    // The subscriptions callbacks, which create a subscription to ROS2 message and a client to gRPC
    using SubscriberRegisterCallback_t = std::function<rclcpp::SubscriptionBase::SharedPtr(std::string, rclcpp::Node&)>;
    static std::unordered_map<std::string, SubscriberRegisterCallback_t> subscriber_registration_callbacks;

    // The actual subscribers and publishers used
    std::unordered_map<std::string, rclcpp::PublisherBase::SharedPtr> publishers;
    std::unordered_map<std::string, rclcpp::SubscriptionBase::SharedPtr> subscribers;

    // The gRPC communication channel
    std::unique_ptr<grpc::Server> grpc_server;
    std::thread grpc_server_thread;
};

std::unordered_map<std::string, BridgeServerROS2::PublisherRegisterCallback_t> BridgeServerROS2::publisher_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS2::SubscriberRegisterCallback_t> BridgeServerROS2::subscriber_registration_callbacks;

// Inlcude our auto-generated files, which populate the registration callback variables
// #include <bridge_types.hpp>

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);
    auto node = std::make_shared<BridgeServerROS2>("bridge_server_ros2");
    rclcpp::spin(node);
}