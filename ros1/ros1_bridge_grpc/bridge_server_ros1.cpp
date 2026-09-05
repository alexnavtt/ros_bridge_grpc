#include <any>
#include <memory>
#include <string>
#include <thread>
#include <random>
#include <cstdlib>
#include <filesystem>
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

        // Retrieve the list of services and their types for which to create bridges
        std::vector<std::string> registered_services_param = nh.param("registered_services", std::vector<std::string>{});

        // Retrieve the channel on which to create the grpc server
        const std::string local_server_address_default = "localhost:50052";
        std::string local_server_address = nh.param("side_b_server_address", local_server_address_default);
        
        const std::string remote_server_address_default = "localhost:50051";
        std::string remote_server_address = nh.param("side_a_server_address", remote_server_address_default);

        // If the server address is a socket, delete it if it exists and append the URI spec
        if (std::filesystem::path(local_server_address).extension() == ".sock") {
            if (std::filesystem::exists(local_server_address)) {
                std::filesystem::remove(local_server_address);
            }
            local_server_address = "unix://" + local_server_address;
        }

        if (std::filesystem::path(remote_server_address).extension() == ".sock") {
            remote_server_address = "unix://" + remote_server_address;
        }

        // Sleep to allow the bridge bringup print statements to separate better
        std::this_thread::sleep_for(std::chrono::seconds(1));

        // Create a gRPC service builder to allow all types to register their publisher callbacks with
        ROS_INFO("Creating gRPC server on %s", local_server_address.c_str());
        grpc::ServerBuilder builder;
        builder.AddListeningPort(local_server_address, grpc::InsecureServerCredentials());

        // Allow larger message size 8MB (default is 4MB)
        builder.SetMaxReceiveMessageSize(8 * 1024 * 1024);
        builder.SetMaxSendMessageSize(8 * 1024 * 1024);
        grpc::ChannelArguments ch_args;
        ch_args.SetMaxReceiveMessageSize(8 * 1024 * 1024);
        ch_args.SetMaxSendMessageSize(8 * 1024 * 1024);

        // Create a gRPC channel to allow all types to register their subscription callbacks with
        ROS_INFO("Creating gRPC client on %s", remote_server_address.c_str());
        std::shared_ptr<grpc::Channel> channel = grpc::CreateCustomChannel(remote_server_address, grpc::InsecureChannelCredentials(), ch_args);

        // For each of them, register the corresponding communication elements
        std::string type;
        for (const std::string& topic : registered_topics_param) {
            bool latched = false;

            if (!nh.getParam(topic + "/type", type)) {
                ROS_ERROR("Missing required message type parameter for topic %s", topic.c_str());
                continue;
            }

            nh.getParam(topic + "/transient_local", latched);

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
            publishers[topic] = publisher_registration_callbacks.at(type)(topic, nh, builder, latched, false);
            subscribers[topic] = subscriber_registration_callbacks.at(type)(topic, nh, channel, latched, false);
        }

        // For each of them, register the corresponding communication elements
        std::string role;
        for (const std::string& service_name : registered_services_param) {
            if (!nh.getParam(service_name + "/type", type)) {
                ROS_ERROR("Missing required service type parameter for %s", service_name.c_str());
                continue;
            }

            if (!nh.getParam(service_name + "/side_b_role", role)) {
                ROS_ERROR("Missing required role for service %s. Valid options are \"service\" or \"client\"", service_name.c_str());
                continue;
            }

            if (role != "service" && role != "client") {
                ROS_ERROR("Got unknown rol %s for %s. Valid options are \"service\" or \"client\"", role.c_str(), service_name.c_str());
                continue;
            }

            if (!client_registration_callbacks.count(type) || !server_registration_callbacks.count(type)) {
                ROS_ERROR("Requested type %s for service %s is unknown to the bridge server, cannot make a connnection!", type.c_str(), service_name.c_str());
                continue;
            }

            if (registered_topics_and_types.count(service_name)) {
                if (registered_topics_and_types.at(service_name) != type) {
                    ROS_ERROR("Failed to register %s %s using type %s as it clashes with an existing registration with type %s",
                        role.c_str(), service_name.c_str(), type.c_str(), registered_topics_and_types.at(service_name).c_str());
                }
                continue;
            }

            ROS_INFO("Registering %s %s using type %s", role.c_str(), service_name.c_str(), type.c_str());
            registered_topics_and_types[service_name] = type;
            if (role == "client") {
                services[service_name] = server_registration_callbacks.at(type)(service_name, nh, channel);
            } else if (role == "service") {
                clients[service_name] = client_registration_callbacks.at(type)(service_name, nh, builder);
            }
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

    // The publisher registration callbacks, which create a publisher to ROS1 and returns a gRPC service
    using PublisherRegisterCallback_t = std::function<std::any(const std::string&, ros::NodeHandle&, grpc::ServerBuilder&, bool, bool)>;
    static std::unordered_map<std::string, PublisherRegisterCallback_t> publisher_registration_callbacks;

    // The subscriptions callbacks, which create a subscription to ROS1 message and a client to gRPC
    using SubscriberRegisterCallback_t = std::function<std::shared_ptr<ros::Subscriber>(const std::string&, ros::NodeHandle&, std::shared_ptr<grpc::Channel>, bool, bool)>;
    static std::unordered_map<std::string, SubscriberRegisterCallback_t> subscriber_registration_callbacks;

    // The service client callbacks, which create a client for a ROS1 server and a server to gRPC
    using ServiceClientRegisterCallback_t = std::function<std::shared_ptr<grpc::Service>(const std::string&, ros::NodeHandle&, grpc::ServerBuilder&)>;
    static std::unordered_map<std::string, ServiceClientRegisterCallback_t> client_registration_callbacks;

    // The service server callbacks, which create a server for a ROS1 client and a client to gRPC
    using ServiceServerRegisterCallback_t = std::function<std::shared_ptr<ros::ServiceServer>(const std::string&, ros::NodeHandle&, std::shared_ptr<grpc::Channel>)>;
    static std::unordered_map<std::string, ServiceServerRegisterCallback_t> server_registration_callbacks;

    // The actual subscribers and publishers used
    std::unordered_map<std::string, std::any> publishers;
    std::unordered_map<std::string, std::shared_ptr<ros::Subscriber>> subscribers;
    std::unordered_map<std::string, std::shared_ptr<grpc::Service>> clients;
    std::unordered_map<std::string, std::shared_ptr<ros::ServiceServer>> services;

    // The gRPC communication channel
    std::unique_ptr<grpc::Server> grpc_server;
    std::thread grpc_server_thread;

    std::unique_ptr<grpc::ServerCompletionQueue> grpc_queue;
    std::thread grpc_queue_thread;
};

std::unordered_map<std::string, BridgeServerROS1::PublisherRegisterCallback_t> BridgeServerROS1::publisher_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS1::SubscriberRegisterCallback_t> BridgeServerROS1::subscriber_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS1::ServiceClientRegisterCallback_t> BridgeServerROS1::client_registration_callbacks;
std::unordered_map<std::string, BridgeServerROS1::ServiceServerRegisterCallback_t> BridgeServerROS1::server_registration_callbacks;

// Inlcude our auto-generated files, which populate the registration callback variables
void registerAllTypes() {
    #include <ros1/register_types.hpp>
}

// Global UID
std::string uid;

int main(int argc, char* argv[]) {
    ros::init(argc, argv, "bridge_server_ros1");
    ros::NodeHandle nh;
    registerAllTypes();
    std::srand(std::hash<std::thread::id>{}(std::this_thread::get_id()));
    uid = std::to_string(std::rand());
    auto server = BridgeServerROS1(nh);

    const char* ros_distro_str = std::getenv("ROS_DISTRO");
    const char* ros_ip_string = std::getenv("ROS_IP");
    const char* ros_hostname_string = std::getenv("ROS_HOSTNAME");
    const char* ros_master_uri_string = std::getenv("ROS_MASTER_URI");
    ROS_INFO("Using\n\tROS_DISTRO: %s\n\tROS_IP: %s\n\tROS_HOSTNAME: %s\n\tROS_MASTER_URI: %s\n\tUID: %s", ros_distro_str, ros_ip_string, ros_hostname_string, ros_master_uri_string, uid.c_str());
    ros::spin();
}
