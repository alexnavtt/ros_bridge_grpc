#include <thread>
#include <type_traits>
#include <unordered_set>
#include <unordered_map>
#include <rclcpp/rclcpp.hpp>
#include <grpcpp/grpcpp.h>
#include <register.hpp>
#include <ros2/bridge_types.hpp>

template<typename T>
constexpr bool is_basic_v() {
    // Returns true for all types that are basic types in ROS
    return std::is_arithmetic<T>::value || std::is_same<T, std::string>::value || std::is_same<T, std::wstring>::value;
}

class BridgeServerROS2 : public rclcpp::Node {
public:
    BridgeServerROS2(const std::string& name) : Node(name)
    {
        RCLCPP_INFO(get_logger(), "Starting ROS2 bridge server");
        // Retrieve the list of topics and types for which to create bridges
        rcl_interfaces::msg::ParameterDescriptor registered_topics_config;
        registered_topics_config.name = "registered_topics";
        registered_topics_config.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING_ARRAY;
        registered_topics_config.description = "The list of topics and types to bridge in the form /my_namespace/my_topic:MyMessagePackage/MyMessageType";
        registered_topics_config.read_only = true;
        std::vector<std::string> registered_topics_param = declare_parameter(registered_topics_config.name, std::vector<std::string>{}, registered_topics_config);

        // Retrieve the channel on which to perform gRPC communication
        rcl_interfaces::msg::ParameterDescriptor grpc_address_config;
        const std::string grpc_address_default = "localhost:50051";
        grpc_address_config.name = "grpc_address";
        grpc_address_config.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING;
        grpc_address_config.description = "The channel on which to perform gRPC communication in the format 'channel_ip_address:port_number'. Default localhost:50051";
        grpc_address_config.read_only = true;
        const std::string grpc_address = declare_parameter(grpc_address_config.name, grpc_address_default, grpc_address_config);

        // Create a gRPC service builder to allow all types to register their publisher callbacks with
        RCLCPP_INFO(get_logger(), "Creating gRPC server on %s", grpc_address.c_str());
        grpc::ServerBuilder builder;
        builder.AddListeningPort(grpc_address, grpc::InsecureServerCredentials());

        // Create a gRPC channel to allow all types to register their subscription callbacks with
        RCLCPP_INFO(get_logger(), "Creating gRPC channel to %s", grpc_address.c_str());
        std::shared_ptr<grpc::Channel> channel = grpc::CreateChannel(grpc_address, grpc::InsecureChannelCredentials());

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

            RCLCPP_INFO(get_logger(), "Registering topic %s using type %s", topic.c_str(), type.c_str());
            registered_topics_and_types[topic] = type;
            publishers[topic] = publisher_registration_callbacks.at(type)(topic, *this, builder);
            subscribers[topic] = subscriber_registration_callbacks.at(type)(topic, *this, channel);
        }

        grpc_queue = builder.AddCompletionQueue();
        grpc_queue_thread = std::thread([this](){
            void* tag;
            bool ok;
            while (grpc_queue->Next(&tag, &ok)) {
                if (!ok) {
                    RCLCPP_ERROR(get_logger(), "gRPC call failed");
                }
            }
        });

        // Finalize the gRPC server
        RCLCPP_INFO(get_logger(), "Starting gRPC server");
        grpc_server = builder.BuildAndStart();
        grpc_server_thread = std::thread([this](){grpc_server->Wait();});
    }

    // The names of the topics we'd like to bridge and the types they're registered to
    std::unordered_map<std::string, std::string> registered_topics_and_types;

    // The publisher registration callbacks, which create a publisher to ROS2 and returns a gRPC service
    using PublisherRegisterCallback_t = std::function<std::shared_ptr<grpc::Service>(std::string, rclcpp::Node&, grpc::ServerBuilder&)>;
    static std::unordered_map<std::string, PublisherRegisterCallback_t> publisher_registration_callbacks;

    // The subscriptions callbacks, which create a subscription to ROS2 message and a client to gRPC
    using SubscriberRegisterCallback_t = std::function<rclcpp::SubscriptionBase::SharedPtr(std::string, rclcpp::Node&, std::shared_ptr<grpc::Channel>)>;
    static std::unordered_map<std::string, SubscriberRegisterCallback_t> subscriber_registration_callbacks;

    // The actual subscribers and publishers used
    std::unordered_map<std::string, std::shared_ptr<grpc::Service>> publishers;
    std::unordered_map<std::string, rclcpp::SubscriptionBase::SharedPtr> subscribers;

    // The gRPC communication channel
    std::unique_ptr<grpc::Server> grpc_server;
    std::thread grpc_server_thread;

    std::unique_ptr<grpc::ServerCompletionQueue> grpc_queue;
    std::thread grpc_queue_thread;
};

std::unordered_map<std::string, BridgeServerROS2::PublisherRegisterCallback_t> BridgeServerROS2::publisher_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS2::SubscriberRegisterCallback_t> BridgeServerROS2::subscriber_registration_callbacks;

void registerAllTypes() {
    #include <ros2/register_types.hpp>
}

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);
    registerAllTypes();
    auto node = std::make_shared<BridgeServerROS2>("bridge_server_ros2");
    rclcpp::spin(node);
}