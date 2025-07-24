#include <thread>
#include <filesystem>
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

        // Retrieve the channel on which to create the grpc server
        rcl_interfaces::msg::ParameterDescriptor ros2_server_address_config;
        const std::string ros2_server_address_default = "localhost:50051";
        ros2_server_address_config.name = "ros2_server_address";
        ros2_server_address_config.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING;
        ros2_server_address_config.description = "The first port on which to perform gRPC communication in the format 'channel_ip_address:port_number'. Default localhost:50051";
        ros2_server_address_config.read_only = true;
        std::string ros2_server_address = declare_parameter(ros2_server_address_config.name, ros2_server_address_default, ros2_server_address_config);

        // If the server address is a socket, delete it if it exists and append the URI spec
        if (std::filesystem::path(ros2_server_address).extension() == ".sock") {
            if (std::filesystem::exists(ros2_server_address)) {
                std::filesystem::remove(ros2_server_address);
            }
            ros2_server_address = "unix://" + ros2_server_address;
        }

        // Retrieve the channel on which to create the grpc client
        rcl_interfaces::msg::ParameterDescriptor ros1_server_address_config;
        const std::string ros1_server_address_default = "localhost:50052";
        ros1_server_address_config.name = "ros1_server_address";
        ros1_server_address_config.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING;
        ros1_server_address_config.description = "The second port on which to perform gRPC communication in the format 'channel_ip_address:port_number'. Default localhost:50052";
        ros1_server_address_config.read_only = true;
        std::string ros1_server_address = declare_parameter(ros1_server_address_config.name, ros1_server_address_default, ros1_server_address_config);

        if (std::filesystem::path(ros1_server_address).extension() == ".sock") {
            ros1_server_address = "unix://" + ros1_server_address;
        }

        // Create a gRPC service builder to allow all types to register their publisher callbacks with
        RCLCPP_INFO(get_logger(), "Creating gRPC server on %s", ros2_server_address.c_str());
        grpc::ServerBuilder builder;
        builder.AddListeningPort(ros2_server_address, grpc::InsecureServerCredentials());

        // Create a gRPC channel to allow all types to register their subscription callbacks with
        RCLCPP_INFO(get_logger(), "Creating gRPC client on %s", ros1_server_address.c_str());
        std::shared_ptr<grpc::Channel> channel = grpc::CreateChannel(ros1_server_address, grpc::InsecureChannelCredentials());

        // For each of them, register the corresponding communication elements
        rcl_interfaces::msg::ParameterDescriptor topic_type_param;
        topic_type_param.type = rcl_interfaces::msg::ParameterType::PARAMETER_STRING;
        rcl_interfaces::msg::ParameterDescriptor transient_local_param;
        transient_local_param.type = rcl_interfaces::msg::ParameterType::PARAMETER_BOOL;
        rcl_interfaces::msg::ParameterDescriptor best_effort_param;
        best_effort_param.type = rcl_interfaces::msg::ParameterType::PARAMETER_BOOL;
        for (const std::string& topic : registered_topics_param) {
            topic_type_param.name = topic + ".type";
            const std::string type = declare_parameter<std::string>(topic_type_param.name, topic_type_param);
            
            transient_local_param.name = topic + ".transient_local";
            const bool is_transient_local = declare_parameter(transient_local_param.name, false, transient_local_param);

            best_effort_param.name = topic + ".best_effort";
            const bool is_best_effort = declare_parameter(best_effort_param.name, false, best_effort_param);

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
            publishers[topic] = publisher_registration_callbacks.at(type)(topic, *this, builder, is_transient_local, is_best_effort);
            subscribers[topic] = subscriber_registration_callbacks.at(type)(topic, *this, channel, is_transient_local, is_best_effort);
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
    using PublisherRegisterCallback_t = std::function<std::shared_ptr<grpc::Service>(const std::string&, rclcpp::Node&, grpc::ServerBuilder&, bool, bool)>;
    static std::unordered_map<std::string, PublisherRegisterCallback_t> publisher_registration_callbacks;

    // The subscriptions callbacks, which create a subscription to ROS2 message and a client to gRPC
    using SubscriberRegisterCallback_t = std::function<rclcpp::SubscriptionBase::SharedPtr(const std::string&, rclcpp::Node&, std::shared_ptr<grpc::Channel>, bool, bool)>;
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