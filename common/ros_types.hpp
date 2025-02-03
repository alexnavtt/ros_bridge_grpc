#pragma once

#ifdef ROS1
#include <ros/ros.h>
#define SUBSCRIBER ros::Subscriber
#define PUBLISHER  ros::Publisher 
#define NODE ros::NodeHandle&
#define LOG_INFO(node, ...) ROS_INFO(__VA_ARGS__)
#define PUBLISHER(type) ros::Publisher
#define PUBLISHER_BASE ros::Publisher
#define SUBSCRIBER(type) ros::Subscriber
#define SUBSCRIBER_BASE ros::Subscriber
#define CREATE_PUB_POINTER(node, type, topic) std::make_shared<ros::Publisher>(node.advertise<type>(topic, 10))
#define CREATE_SUB_POINTER(node, type, topic, callback) std::make_shared<ros::Subscriber>(node.subscribe<type>(topic, 10, callback))
#endif

#ifdef ROS2
#include <rclcpp/rclcpp.hpp>
#define NODE rclcpp::Node&
#define LOG_INFO(node, ...) RCLCPP_INFO(node.get_logger(), __VA_ARGS__)
#define PUBLISHER(type) rclcpp::Publisher<type>
#define PUBLISHER_BASE rclcpp::PublisherBase
#define SUBSCRIBER(type) rclcpp::Subscription<type>
#define SUBSCRIBER_BASE rclcpp::SubscriptionBase
#define CREATE_PUB_POINTER(node, type, topic) node.create_publisher<type>(topic, 10)
#define CREATE_SUB_POINTER(node, type, topic, callback) node.create_subscription<type>(topic, 10, callback)
#endif
