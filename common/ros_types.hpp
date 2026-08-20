#pragma once

#ifdef ROS1
#include <ros/ros.h>
#define NODE ros::NodeHandle&
#define LOG_INFO(node, ...) ROS_INFO(__VA_ARGS__)
#define PUBLISHER(type) ros::Publisher
#define PUBLISHER_BASE ros::Publisher
#define SUBSCRIBER(type) ros::Subscriber
#define SUBSCRIBER_BASE ros::Subscriber
#define CREATE_PUB_POINTER(node, type, topic, is_transient_local, is_best_effort) std::make_shared<ros::Publisher>(node.advertise<type>(topic, 10, is_transient_local))
#define BOOST_CALLBACK_FN_TYPE(type) boost::function<void(const ros::MessageEvent<type>&)>
#define CREATE_SUB_POINTER(node, type, topic, callback, is_transient_local, is_best_effort) std::make_shared<ros::Subscriber>(node.subscribe<type>(topic, 10, static_cast<BOOST_CALLBACK_FN_TYPE(type)>(callback)))
#endif

#ifdef ROS2
#include <rclcpp/rclcpp.hpp>
#define NODE rclcpp::Node&
#define LOG_INFO(node, ...) RCLCPP_INFO(node.get_logger(), __VA_ARGS__)
#define PUBLISHER(type) rclcpp::Publisher<type>
#define PUBLISHER_BASE rclcpp::PublisherBase
#define SUBSCRIBER(type) rclcpp::Subscription<type>
#define SUBSCRIBER_BASE rclcpp::SubscriptionBase
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
#endif

// Custom UID for each bridge instance
#include <string>
extern std::string uid;
