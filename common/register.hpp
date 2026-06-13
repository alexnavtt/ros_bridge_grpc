#pragma once

#include <any>
#include <memory>
#include <ros_types.hpp>
#include <grpcpp/grpcpp.h>

template<typename T>
std::shared_ptr<SUBSCRIBER_BASE> registerSubscription(const std::string&, NODE, std::shared_ptr<grpc::Channel>, bool transient_local = false, bool best_effort = false);

template<typename T>
std::shared_ptr<grpc::Service> registerPublisher(const std::string&, NODE, grpc::ServerBuilder&, bool transient_local = false, bool best_effort = false);

template<typename T>
std::shared_ptr<SERVICE_SERVER_BASE> registerServiceServer(const std::string&, NODE, std::shared_ptr<grpc::Channel>);

template<typename T>
std::shared_ptr<grpc::Service> registerServiceClient(const std::string&, NODE, grpc::ServerBuilder&);

template<typename ros_type, typename proto_type>
void ros2grpc(const ros_type&, proto_type&);

template<typename ros_type, typename proto_type>
void grpc2ros(const proto_type&, ros_type&);
