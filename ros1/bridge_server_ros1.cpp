#include <any>
#include <thread>
#include <type_traits>
#include <unordered_set>
#include <unordered_map>
#include <ros/ros.h>
#include <grpcpp/grpcpp.h>
#include <register.hpp>
#include <ros1/bridge_types.hpp>

template<typename T>
constexpr bool is_basic_v() {
    // Returns true for all types that are basic types in ROS
    return std::is_arithmetic<T>::value || std::is_same<T, std::string>::value || std::is_same<T, std::wstring>::value;
}

class BridgeServerROS1 {
public:
    BridgeServerROS1(ros::NodeHandle& nh)
    {
        ROS_INFO("Starting ROS1 bridge server");
        // Retrieve the list of topics and types for which to create bridges
        std::vector<std::string> registered_topics_param = nh.param("registered_topics", std::vector<std::string>{});

        // Retrieve the channel on which to perform gRPC communication
        const std::string grpc_address_default = "localhost:50051";
        const std::string grpc_address = nh.param("grpc_address", grpc_address_default);

        // Create a gRPC service builder to allow all types to register their publisher callbacks with
        ROS_INFO("Creating gRPC server on %s", grpc_address.c_str());
        grpc::ServerBuilder builder;
        builder.AddListeningPort(grpc_address, grpc::InsecureServerCredentials());

        // Create a gRPC channel to allow all types to register their subscription callbacks with
        std::shared_ptr<grpc::Channel> channel = grpc::CreateChannel(grpc_address, grpc::InsecureChannelCredentials());

        // For each of them, register the corresponding communication elements
        for (const std::string& topic_name_and_type : registered_topics_param) {
            const std::size_t delim = topic_name_and_type.find(':');
            const std::string topic = topic_name_and_type.substr(0, delim);
            const std::string type  = topic_name_and_type.substr(delim+1); 

            if (!publisher_registration_callbacks.count(type) || !subscriber_registration_callbacks.count(type)) {
                ROS_ERROR("Requested type %s for topic %s is unknown to the bridge server, cannot make a connnection!", type.c_str(), topic.c_str());
                continue;
            }

            if (registered_topics_and_types.count(topic)) {
                if (registered_topics_and_types.at(topic) != type) {
                    ROS_ERROR("Failed to register topic %s using type %s as it clashes with an existing registration with type %s",
                        topic.c_str(), type.c_str(), registered_topics_and_types.at(topic).c_str());
                }
                continue;
            }

            ROS_INFO("Registering topic %s using type %s", topic.c_str(), type.c_str());
            registered_topics_and_types[topic] = type;
            publishers[topic] = publisher_registration_callbacks.at(type)(topic, nh, builder);
            subscribers[topic] = subscriber_registration_callbacks.at(type)(topic, nh, channel);
        }

        grpc_queue = builder.AddCompletionQueue();
        grpc_queue_thread = std::thread([this](){
            void* tag;
            bool ok;
            while (grpc_queue->Next(&tag, &ok)) {
                if (!ok) {
                    ROS_ERROR("gRPC call failed");
                }
            }
        });

        // Finalize the gRPC server
        grpc_server = builder.BuildAndStart();
        grpc_server_thread = std::thread([this](){grpc_server->Wait();});
        ROS_INFO("Server online");
    }

    // The names of the topics we'd like to bridge and the types they're registered to
    std::unordered_map<std::string, std::string> registered_topics_and_types;

    // The publisher registration callbacks, which create a publisher to ROS2 and returns a gRPC service
    using PublisherRegisterCallback_t = std::function<std::any(std::string, ros::NodeHandle&, grpc::ServerBuilder&)>;
    static std::unordered_map<std::string, PublisherRegisterCallback_t> publisher_registration_callbacks;

    // The subscriptions callbacks, which create a subscription to ROS2 message and a client to gRPC
    using SubscriberRegisterCallback_t = std::function<std::shared_ptr<ros::Subscriber>(std::string, ros::NodeHandle&, std::shared_ptr<grpc::Channel>)>;
    static std::unordered_map<std::string, SubscriberRegisterCallback_t> subscriber_registration_callbacks;

    // The actual subscribers and publishers used
    std::unordered_map<std::string, std::any> publishers;
    std::unordered_map<std::string, std::shared_ptr<ros::Subscriber>> subscribers;

    // The gRPC communication channel
    std::unique_ptr<grpc::Server> grpc_server;
    std::thread grpc_server_thread;

    std::unique_ptr<grpc::ServerCompletionQueue> grpc_queue;
    std::thread grpc_queue_thread;
};

std::unordered_map<std::string, BridgeServerROS1::PublisherRegisterCallback_t> BridgeServerROS1::publisher_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS1::SubscriberRegisterCallback_t> BridgeServerROS1::subscriber_registration_callbacks;

// Inlcude our auto-generated files, which populate the registration callback variables
void registerAllTypes() {
    #include <ros1/register_types.hpp>
}

int main(int argc, char* argv[]) {
    ros::init(argc, argv, "bridge_server_ros1");
    ros::NodeHandle nh;
    auto server = BridgeServerROS1(nh);
    ros::spin();
}