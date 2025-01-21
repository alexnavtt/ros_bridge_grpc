#pragma once

#include <any>
#include <memory>
#include <ros_types.hpp>
#include <grpcpp/grpcpp.h>

template<typename T>
std::shared_ptr<SUBSCRIBER> registerSubscription(const std::string&, NODE, std::shared_ptr<grpc::Channel>) {
    static_assert(false, "Called registerSubscription with unknown type");
}

template<typename T>
std::any registerPublisher(const std::string&, NODE, grpc::ServerBuilder&) {
    static_assert(false, "Called registerPublisher with unknown type");
}
