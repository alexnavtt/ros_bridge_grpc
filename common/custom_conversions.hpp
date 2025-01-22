#include "google/protobuf/duration.pb.h"
#include "google/protobuf/timestamp.pb.h"

#ifdef ROS2
#include "builtin_interfaces/msg/time.hpp" 
#include "builtin_interfaces/msg/duration.hpp"
#include "std_msgs/msg/header.hpp"
#include "std_msgs.Header.pb.h"
#endif

void ros2grpc(const builtin_interfaces::msg::Time& ros_msg, google::protobuf::Timestamp& proto_msg) {
    proto_msg.set_seconds(ros_msg.sec);
    proto_msg.set_nanos(ros_msg.nanosec);
}

void grpc2ros(const google::protobuf::Timestamp& proto_msg, builtin_interfaces::msg::Time& ros_msg) {
    ros_msg.sec = proto_msg.seconds();
    ros_msg.nanosec = proto_msg.nanos();
}

void ros2grpc(const builtin_interfaces::msg::Duration& ros_msg, google::protobuf::Duration& proto_msg) {
    proto_msg.set_seconds(ros_msg.sec);
    proto_msg.set_nanos(ros_msg.nanosec);
}

void grpc2ros(const google::protobuf::Duration& proto_msg, builtin_interfaces::msg::Duration& ros_msg) {
    ros_msg.sec = proto_msg.seconds();
    ros_msg.nanosec = proto_msg.nanos();
}
