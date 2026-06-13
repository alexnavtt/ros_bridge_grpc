#pragma once
#include "google/protobuf/duration.pb.h"
#include "google/protobuf/timestamp.pb.h"

#ifdef ROS2
#include "builtin_interfaces/msg/time.hpp" 
#include "builtin_interfaces/msg/duration.hpp"
#include "std_msgs/msg/header.hpp"
#include "std_msgs.msg.Header.pb.h"
#define ROS_TIME builtin_interfaces::msg::Time
#define ROS_DURATION builtin_interfaces::msg::Duration
#define NANOSECONDS nanosec
#endif

#ifdef ROS1
#include "ros/time.h"
#include "ros/duration.h"
#define ROS_TIME ros::Time
#define ROS_DURATION ros::Duration
#define NANOSECONDS nsec
#endif

static inline void ros2grpc(const ROS_TIME& ros_msg, google::protobuf::Timestamp& proto_msg) {
    proto_msg.set_seconds(ros_msg.sec);
    proto_msg.set_nanos(ros_msg.NANOSECONDS);
}

static inline void grpc2ros(const google::protobuf::Timestamp& proto_msg, ROS_TIME& ros_msg) {
    ros_msg.sec = proto_msg.seconds();
    ros_msg.NANOSECONDS = proto_msg.nanos();
}

static inline void ros2grpc(const ROS_DURATION& ros_msg, google::protobuf::Duration& proto_msg) {
    proto_msg.set_seconds(ros_msg.sec);
    proto_msg.set_nanos(ros_msg.NANOSECONDS);
}

static inline void grpc2ros(const google::protobuf::Duration& proto_msg, ROS_DURATION& ros_msg) {
    ros_msg.sec = proto_msg.seconds();
    ros_msg.NANOSECONDS = proto_msg.nanos();
}

static inline void ros2grpc(const std::vector<unsigned char>& ros_msg, std::string& proto_msg) {
    proto_msg.assign(ros_msg.begin(), ros_msg.end());
}

static inline void grpc2ros(const std::string& proto_msg, std::vector<unsigned char>& ros_msg) {
    ros_msg.assign(proto_msg.begin(), proto_msg.end());
}

static inline void ros2grpc(const std::vector<signed char>& ros_msg, std::string& proto_msg) {
    proto_msg.assign(ros_msg.begin(), ros_msg.end());
}

static inline void grpc2ros(const std::string& proto_msg, std::vector<signed char>& ros_msg) {
    ros_msg.assign(proto_msg.begin(), proto_msg.end());
}