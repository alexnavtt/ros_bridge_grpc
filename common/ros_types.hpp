#pragma once

#ifdef ROS1
#include <ros/ros.h>
#define SUBSCRIBER ros::Subscriber
#define PUBLISHER  ros::Publisher 
#define NODE ros::NodeHandle&
#endif

#ifdef ROS2
#include <rclcpp/rclcpp.hpp>
#define SUBSCRIBER rclcpp::SubscriptionBase
#define PUBLISHER  rclcpp::PublisherBase 
#define NODE rclcpp::Node::SharedPtr
#endif
