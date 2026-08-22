#pragma once

#ifdef ROS1
#include <ros/ros.h>
#define NODE ros::NodeHandle&
#define LOG_INFO(node, ...) ROS_INFO(__VA_ARGS__)
#define PUBLISHER(type) ros::Publisher
#define PUBLISHER_BASE ros::Publisher
#define SUBSCRIBER(type) ros::Subscriber
#define SUBSCRIBER_BASE ros::Subscriber
#define SERVICE_SERVER(type) ros::ServiceServer
#define SERVICE_SERVER_BASE ros::ServiceServer
#define SERVICE_CLIENT(type) ros::ServiceClient
#define SERVICE_CLIENT_BASE ros::ServiceClient
#define CREATE_PUB_POINTER(node, type, topic, is_transient_local, is_best_effort) std::make_shared<ros::Publisher>(node.advertise<type>(topic, 10, is_transient_local))
#define BOOST_CALLBACK_FN_TYPE(type) boost::function<void(const ros::MessageEvent<type>&)>
#define CREATE_SUB_POINTER(node, type, topic, callback, is_transient_local, is_best_effort) std::make_shared<ros::Subscriber>(node.subscribe<type>(topic, 10, static_cast<BOOST_CALLBACK_FN_TYPE(type)>(callback)))
#define CREATE_CLIENT_POINTER(node, type, name) std::make_shared<ros::ServiceClient>(node.serviceClient<type>(name))
#define CREATE_SERVER_POINTER(node, type, name, callback) std::make_shared<ros::ServiceServer>(node.advertiseService(name, boost::function<bool(type::Request&, type::Response&)>(callback)))
#define ASYNC_SEND_REQUEST(client_, ros_request, service_type, callback) \
    {auto t_func = [client=client_, ros_request, callback]() { \
        auto service_obj = service_type{}; \
        service_obj.request = *ros_request; \
        const bool success = client->call(service_obj); \
        callback(success ? std::make_shared<service_type::Response>(service_obj.response) : std::shared_ptr<service_type::Response>()); \
    }; std::thread(t_func).detach();}
#endif

#ifdef ROS2
#include <rclcpp/rclcpp.hpp>
#define NODE rclcpp::Node&
#define LOG_INFO(node, ...) RCLCPP_INFO(node.get_logger(), __VA_ARGS__)
#define PUBLISHER(type) rclcpp::Publisher<type>
#define PUBLISHER_BASE rclcpp::PublisherBase
#define SUBSCRIBER(type) rclcpp::Subscription<type>
#define SUBSCRIBER_BASE rclcpp::SubscriptionBase
#define SERVICE_CLIENT(type) rclcpp::Client<type> 
#define SERVICE_CLIENT_BASE rclcpp::ClientBase
#define SERVICE_SERVER(type) rclcpp::Service<type>
#define SERVICE_SERVER_BASE rclcpp::ServiceBase
#define CREATE_PUB_POINTER(node, type, topic, is_transient_local, is_best_effort) \
    [&node, &topic, is_transient_local, is_best_effort] () { \
        rclcpp::QoS qos(10); \
        if (is_transient_local) qos.transient_local(); \
        if (is_best_effort) qos.best_effort(); \
        return node.create_publisher<type>(topic, qos); \
    }();
#define CREATE_SUB_POINTER(node, type, topic, callback, is_transient_local, is_best_effort) \
    [&node, &topic, &callback, is_transient_local, is_best_effort] () { \
        rclcpp::SubscriptionOptionsWithAllocator<std::allocator<void>> opts; \
        opts.ignore_local_publications = true; \
        rclcpp::QoS qos(10); \
        if (is_transient_local) qos.transient_local(); \
        if (is_best_effort) qos.best_effort(); \
        return node.create_subscription<type>(topic, qos, callback, opts); \
    }();
#define CREATE_CLIENT_POINTER(node, type, name) \
    [&node, &name] () { \
        return node.create_client<type>(name); \
    }();
#define CREATE_SERVER_POINTER(node, type, name, callback) \
    [&node, &name, callback] () { \
        return node.create_service<type>(name, callback);\
    }();
#define ASYNC_SEND_REQUEST(client_, ros_request, service_type, callback) \
    {auto c_func = [callback](std::shared_future<std::shared_ptr<service_type::Response>> future){ \
        callback(future.get()); \
    }; client_->async_send_request(ros_request, c_func);}
#endif

// Custom UID for each bridge instance
#include <string>
extern std::string uid;
