import re
import os
import sys
import typing
from pathlib import Path
from proto_schema_parser import Parser, Message, FieldCardinality
from proto_schema_parser.ast import Field

ros_basic_types = [
    'bool', 
    'int', 'uint', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64',
    'float32', 'float64', 'float', 'double',
    'string'
]

def to_snake(name: str) -> str:
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name).lower()

class FileMetadata:
    def __init__(self, proto_path: str, mode: str):
        self.proto_path = proto_path
        self.filename = os.path.basename(proto_path)
        self.msg_package, self.msg_class, self.msg_type, _ = self.filename.split('.')
        self.mode = mode
        self.conversion_filename = f'convert_{self.msg_package}_{self.msg_type}.cpp'

        # Define what the C++ types are called in this ROS version for this message/service type
        if self.mode == 'ros1':
            self.ros_type = f'{self.msg_package}::{self.msg_type}' # eg. std_msgs::String or std_srvs::SetBool
            self.header = f'{self.msg_package}/{self.msg_type}.h'  # eg. std_msgs/String.h or std_srvs/SetBool.h
            self.pointer = 'ConstPtr'                              # eg. std_msgs::String::ConstPtr

        elif self.mode == 'ros2':
            self.ros_type = f'{self.msg_package}::{self.msg_class}::{self.msg_type}'                   # eg. std_msgs::msg::String or std_srvs::srv::SetBool
            self.header = f'{self.msg_package}/{self.msg_class}/{to_snake(self.msg_type)}.hpp'         # eg. std_msgs/msg/string.hpp or std_srvs/srv/set_bool.hpp
            self.foxy = os.environ['SIDE_A_DISTRO'] == "foxy" or os.environ['SIDE_B_DISTRO'] == 'foxy' # eg. Handle foxy-specific service issues
            self.pointer = 'ConstSharedPtr'                                                            # eg. std_msgs::msg::String::ConstSharedPtr

        if self.msg_class == 'msg':
            self.ros_type = [self.ros_type]
            self.proto_type = [f'{self.msg_package}_{self.msg_class}_proto::{self.msg_type}']
        elif self.msg_class == 'srv':
            self.service_type = self.ros_type
            self.ros_type = [f'{self.ros_type}::Request', f'{self.ros_type}::Response']
            self.proto_type = [f'{self.msg_package}_{self.msg_class}_proto::{self.msg_type}Request', f'{self.msg_package}_{self.msg_class}_proto::{self.msg_type}Response']

        # Extract the individual fields of the message, if they're builtin or ROS types, and if they're repeated or not
        with open(proto_path, 'r') as f:
            proto_data = Parser().parse(f.read())

        self.basic_fields = []
        self.message_fields = []
        for element in proto_data.file_elements:
            if not isinstance(element, Message): continue
            
            self.basic_fields.append([])
            self.message_fields.append([])
            for proto_field in element.elements:
                if not isinstance(proto_field, Field): continue

                is_repeated = proto_field.cardinality == FieldCardinality.REPEATED
                if proto_field.type in ros_basic_types:
                    self.basic_fields[-1].append((proto_field.name, proto_field.type, is_repeated))
                else:
                    self.message_fields[-1].append((proto_field.name, proto_field.type, is_repeated))

            # For message files we stop after the first message, which is the ROS message definition
            if self.msg_class == 'msg':
                break
            # For service files we stop after the first two messages, which are the request and response definitions
            elif self.msg_class == 'srv':
                if len(self.basic_fields) == 2:
                    break

def add_subscription_generator_callback(file_metadata: FileMetadata, dest_path: str) -> None:
    ros_type = file_metadata.ros_type[0]
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    pointer = file_metadata.pointer
    mode = file_metadata.mode
    proto_type = file_metadata.proto_type[0]
    
    with open(os.path.join(dest_path, file_metadata.conversion_filename), 'a') as f:
        f.write(
            f'template<>\n'
            f'std::shared_ptr<SUBSCRIBER_BASE> registerSubscription<{ros_type}>(const std::string& topic, NODE nh, std::shared_ptr<grpc::Channel> channel, [[maybe_unused]] bool transient_local, [[maybe_unused]] bool best_effort) {"{"}\n'
            f'    static std::map<grpc::Channel*, std::unique_ptr<{msg_package}_msg_proto::Send{msg_type}MsgROS::Stub>> stubs;\n'
            f'    if (!stubs.count(channel.get())) {"{"}\n'
            f'        stubs[channel.get()] = std::move({msg_package}_msg_proto::Send{msg_type}MsgROS::NewStub(channel));\n'
            f'    {"}"}\n'
            f'    \n'
            f'    auto& stub = stubs.at(channel.get());\n'
        )

        if mode == 'ros1':
            f.write(
            f'    auto callback = [&stub, topic, &nh](const ros::MessageEvent<const {ros_type}>& event) {"{"}\n'
            f'        // Ignore message from self\n'
            f'        if (event.getPublisherName() == ros::this_node::getName()) return;\n'
            f'        const {ros_type}::{pointer} msg = event.getConstMessage();\n'
            )
        else:
            f.write(
            f'    auto callback = [&stub, topic, &nh](const {ros_type}::{pointer} msg) {"{"}\n'
            )

        f.write(
            f'        {proto_type}Packet proto_message;\n'
            f'        proto_message.set_topic(topic);\n'
            f'        ros2grpc(*msg, *proto_message.mutable_message());\n'
            f'        grpc::ClientContext client_context;\n'
            f'        google::protobuf::Empty empty_message;\n'
            f'        client_context.AddMetadata(uid, "");\n'
            f'        grpc::Status status = stub->SendROSMessage(&client_context, proto_message, &empty_message);\n'
            f'        if (!status.ok()) LOG_INFO(nh, "gRPC call failed sending message type {ros_type} across bridge");\n'
            f'    {"}"};\n'
            f'    \n'
            f'    auto sub = CREATE_SUB_POINTER(nh, {ros_type}, topic, callback, transient_local, best_effort);\n'
            f'    return std::static_pointer_cast<SUBSCRIBER_BASE>(sub);\n'
            f'{"}"}\n\n'
        )

def add_publisher_generator_callback(file_metadata: FileMetadata, dest_path: str) -> None:
    ros_type = file_metadata.ros_type[0]
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    mode = file_metadata.mode
    proto_type = file_metadata.proto_type[0]

    with open(os.path.join(dest_path, file_metadata.conversion_filename), 'a') as f:
        f.write(
            f'template<>\n'
            f'std::shared_ptr<grpc::Service> registerPublisher<{ros_type}>(const std::string& topic, NODE nh, grpc::ServerBuilder& server_builder, bool transient_local, bool best_effort) {"{"}\n'
            f'    class SendROSMessageImpl final : public {msg_package}_msg_proto::Send{msg_type}MsgROS::Service {"{"}\n'
            f'    public:\n'
            f'        grpc::Status SendROSMessage (grpc::ServerContext* context, const {proto_type}Packet* message, google::protobuf::Empty* response) override {"{"}\n'
            f'            if (context->client_metadata().count(uid)) return grpc::Status::OK;\n'
            f'            {ros_type} ros_msg;\n'
            f'            grpc2ros(message->message(), ros_msg);\n'
            f'            if (pubs_.count(message->topic()) == 0) {"{"}\n'
            f'                return grpc::Status(grpc::StatusCode::NOT_FOUND, "Received message on unregistered topic" + message->topic());\n'
            f'            {"}"}\n'
            f'            pubs_.at(message->topic())->publish(ros_msg);\n'
            f'            return grpc::Status::OK;\n'
            f'        {"}"}\n'
            f'    \n'
            f'        void add_topic(NODE node, std::string topic, [[maybe_unused]] bool transient_local, [[maybe_unused]] bool best_effort) {"{"}\n'
            f'            pubs_[topic] = CREATE_PUB_POINTER(node, {ros_type}, topic, transient_local, best_effort);\n'
            f'        {"}"}\n'
            f'    \n'
            f'    private:\n'      
            f'        std::unordered_map<std::string, std::shared_ptr<PUBLISHER({ros_type})>> pubs_;\n'
            f'    {"}"};\n'
            f'    \n'
            f'    static std::shared_ptr<SendROSMessageImpl> service;\n'
            f'    if (!service) {"{"}\n'
            f'        service = std::make_shared<SendROSMessageImpl>();\n'
            f'        server_builder.RegisterService(service.get());\n'
            f'    {"}"}\n'
            f'    service->add_topic(nh, topic, transient_local, best_effort);\n'
            f'    return std::static_pointer_cast<grpc::Service>(service);\n'
            f'{"}"};\n\n'
        )

def add_client_generator_callback(file_metadata: FileMetadata, dest_path: str) -> None:
    ros_req_type, ros_resp_type = file_metadata.ros_type
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    service_type = file_metadata.service_type
    mode = file_metadata.mode

    with open(os.path.join(dest_path, file_metadata.conversion_filename), 'a') as f:
        f.write(
            f'template<>\n'
            f'std::shared_ptr<grpc::Service> registerServiceClient<{service_type}>(const std::string& service_name, NODE nh, grpc::ServerBuilder& server_builder) {"{"}\n'
            f'    class CallROSServiceImpl final : public {msg_package}_srv_proto::Send{msg_type}SrvROS::CallbackService {"{"}\n'
            f'    public:\n'
            f'        grpc::ServerUnaryReactor* CallROSService (grpc::CallbackServerContext* context, const {msg_package}_srv_proto::{msg_type}RequestPacket* request, {msg_package}_srv_proto::{msg_type}ResponsePacket *response) {"{"}\n'
            f'            auto reactor = context->DefaultReactor();\n'
            f'            if (clients_.count(request->service()) == 0) {"{"}\n'
            f'                reactor->Finish(grpc::Status(grpc::StatusCode::NOT_FOUND, "Received service request on unregistered service" + request->service()));\n'
            f'                return reactor;\n'
            f'            {"}"}\n'
            f'            auto ros_request = std::make_shared<{ros_req_type}>();\n'
            f'            grpc2ros(request->request(), *ros_request);\n'
            f'            \n'
            f'            auto callback = [this, service_name = request->service(), response, reactor] (std::shared_ptr<{ros_resp_type}> resp) {"{"}\n'
            f'                if (!resp) {"{"}\n'
            f'                    reactor->Finish(grpc::Status(grpc::StatusCode::INTERNAL, "ROS Service call did not return successfully"));\n'
            f'                    return;\n'
            f'                {"}"}\n'
            f'                try {"{"}\n'
            f'                    response->set_service(service_name);\n'
            f'                    ros2grpc(*resp, *response->mutable_response());\n'
            f'                    reactor->Finish(grpc::Status::OK);\n'
            f'                {"}"} catch (const std::exception& exception) {"{"}\n'
            f'                    reactor->Finish(grpc::Status(grpc::StatusCode::INTERNAL, exception.what()));\n'
            f'                {"}"}\n'
            f'            {"};"}\n'
            f'                \n'
            f'            ASYNC_SEND_REQUEST(clients_.at(request->service()), ros_request, {service_type}, callback);\n'
            f'            return reactor;\n'
            f'        {"}"}\n'
            f'                \n'
            f'        void add_service(NODE node, std::string service_name) {"{"}\n'
            f'            clients_[service_name] = CREATE_CLIENT_POINTER(node, {service_type}, service_name);\n'
            f'        {"}"}\n'
            f'                \n'
            f'    private:\n'
            f'        std::unordered_map<std::string, std::shared_ptr<SERVICE_CLIENT({service_type})>> clients_;\n'
            f'    {"};"}\n\n'
            f'    static std::shared_ptr<CallROSServiceImpl> service_impl;\n'
            f'    if (!service_impl) {"{"}\n'
            f'        service_impl = std::make_shared<CallROSServiceImpl>();\n'
            f'        server_builder.RegisterService(service_impl.get());\n'
            f'    {"}"}\n\n'
            f'    service_impl->add_service(nh, service_name);\n'
            f'    return std::static_pointer_cast<grpc::Service>(service_impl);\n'
            f'{"}"}\n\n'
        )

def add_service_generator_callback(file_metadata: FileMetadata, dest_path: str) -> None:
    ros_req_type, ros_resp_type = file_metadata.ros_type
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    pointer = file_metadata.pointer
    service_type = file_metadata.service_type
    mode = file_metadata.mode

    with open(os.path.join(dest_path, file_metadata.conversion_filename), 'a') as f:
        f.write(
            f'template<>\n'
            f'std::shared_ptr<SERVICE_SERVER_BASE> registerServiceServer<{service_type}>(const std::string& service_name, NODE nh, std::shared_ptr<grpc::Channel> channel) {"{"}\n'
            f'    static std::map<grpc::Channel*, std::unique_ptr<{msg_package}_srv_proto::Send{msg_type}SrvROS::Stub>> stubs;\n'
            f'    if (!stubs.count(channel.get())) {"{"}\n'
            f'        stubs[channel.get()] = std::move({msg_package}_srv_proto::Send{msg_type}SrvROS::NewStub(channel));\n'
            f'    {"}"}\n'
            f'    auto& stub = stubs.at(channel.get());\n'
            f'\n'
        )

        if mode == 'ros1':
            f.write(
            f'    auto request_received_callback = [&stub, &nh, service_name]({ros_req_type}& ros_req, {ros_resp_type}& ros_resp){"{"}\n'
            )
        elif file_metadata.foxy:
            f.write(
            f'    auto request_received_callback = [&stub, &nh, service_name](const {ros_req_type}::SharedPtr ros_req, {ros_resp_type}::SharedPtr ros_resp) -> void {"{"}\n'
            )
        else:
            f.write(
            f'    auto server_holder = std::make_shared<rclcpp::Service<{service_type}>::SharedPtr>();\n'
            f'    auto request_received_callback = [&stub, &nh, server_holder, service_name](const std::shared_ptr<rmw_request_id_t> request_header, const {ros_req_type}::ConstSharedPtr ros_req) -> void {"{"}\n'
            )

        f.write(
            f'        auto request_packet = std::make_shared<{msg_package}_srv_proto::{msg_type}RequestPacket>();\n'
            f'        auto response_packet = std::make_shared<{msg_package}_srv_proto::{msg_type}ResponsePacket>();\n'
            f'        auto client_context = std::make_shared<grpc::ClientContext>();\n'
            f'\n'
            f'        request_packet->set_service(service_name);\n'
            f'\n'
        )
        
        if mode == 'ros1' or file_metadata.foxy:
            f.write(
            f'        ros2grpc({"" if mode == "ros1" else "*"}ros_req, *request_packet->mutable_request());\n'
            f'        grpc::Status status = stub->CallROSService(client_context.get(), *request_packet, response_packet.get());\n'
            f'        if (!status.ok()) LOG_INFO(nh, "gRPC call failed sending service \'%s\' of type \'{service_type}\'  across the bridge: %s\\n%s",\n'
            f'              service_name.c_str(), status.error_message().c_str(), status.error_details().c_str());\n'
            f'        grpc2ros(response_packet->response(), {"" if mode == "ros1" else "*"}ros_resp);\n'
            f'        return {"true" if mode == "ros1" else ""};\n'
            )
        else:
            f.write(
            f'        ros2grpc(*ros_req, *request_packet->mutable_request());\n'
            f'        auto response_received_callback = [&nh, request_packet, response_packet, service_name, server_holder, request_header, client_context](grpc::Status status) -> void {"{"}\n'
            f'            (void) client_context;\n'
            f'            if (!status.ok()) {"{"}\n'
            f'                LOG_INFO(nh, "gRPC call failed sending service \'%s\' of type \'{service_type}\' across the bridge: %s\\n%s",\n'
            f'                  service_name.c_str(), status.error_message().c_str(), status.error_details().c_str());\n'
            f'                return;\n'
            f'            {"}"}\n'
            f'            {ros_resp_type} ros_resp;\n'
            f'            grpc2ros(response_packet->response(), ros_resp);\n'
            f'            (*server_holder)->send_response(*request_header, ros_resp);\n'
            f'        {"}"};\n'
            f'\n'
            f'        stub->async()->CallROSService(client_context.get(), request_packet.get(), response_packet.get(), response_received_callback);\n'
            )

        f.write(
            f'    {"}"};\n'
            f'\n'
            f'    auto server = CREATE_SERVER_POINTER(nh, {service_type}, service_name, request_received_callback);\n'
            f'    {"*server_holder = server;" if mode == "ros2" and not file_metadata.foxy else ""}\n'
            f'    return std::static_pointer_cast<SERVICE_SERVER_BASE>(server);\n'
            f'{"}"}\n\n'
        )

def generate_cpp_conversion_code(file_metadata: FileMetadata, dest_path: str) -> None:
    msg_package = file_metadata.msg_package
    msg_class = file_metadata.msg_class
    msg_type = file_metadata.msg_type
    ros_header = file_metadata.header
    
    filename = f'convert_{msg_package}_{msg_type}.cpp'
    print(f'Generating {filename}')

    with open(os.path.join(dest_path, filename), 'w') as f:
        # Headers
        f.write(
            f'#include <{msg_package}.{msg_class}.{msg_type}.pb.h>\n'
            f'#include <{msg_package}.{msg_class}.{msg_type}.grpc.pb.h>\n'
            f'#include <{ros_header}>\n'
            f'\n'
            f'#include <thread>\n'
            f'#include <register.hpp>\n'
            f'#include <ros_types.hpp>\n'
            f'#include <careful_resize.hpp>\n'
            f'#include <custom_conversions.hpp>\n'
            '\n'
        )

        # Add a function to convert this message type from ros to grpc
        for ros_type, proto_type, basic_fields, message_files in zip(file_metadata.ros_type, file_metadata.proto_type, file_metadata.basic_fields, file_metadata.message_fields):
            f.write(f'template<>\n')
            f.write(f'void ros2grpc<{ros_type}, {proto_type}>(const {ros_type}& ros_msg, {proto_type}& proto_msg) {"{"}\n')
            for field_name, field_type, is_repeated in basic_fields:
                if is_repeated:
                    f.write(f'    proto_msg.mutable_{field_name}()->Assign(std::begin(ros_msg.{field_name}), std::end(ros_msg.{field_name}));\n')
                else:
                    f.write(f'    proto_msg.set_{field_name}(ros_msg.{field_name});\n')
                    
            for field_name, field_type, is_repeated in message_files:
                if field_name == '__ros_bridge_grpc_empty_msg': continue
                if is_repeated:
                    f.write(
                        f'    for (const auto& field : ros_msg.{field_name}) {"{"}\n'
                        f'        auto* msg_field = proto_msg.add_{field_name}();\n'
                        f'        ros2grpc(field, *msg_field);\n'
                        f'    {"}"}\n'
                    )
                else:
                    f.write(f'    ros2grpc(ros_msg.{field_name}, *proto_msg.mutable_{field_name}());\n')
            f.write("}\n\n")

            # Add a function to convert this message type from ros to grpc
            f.write(f'template<>\n')
            f.write(f'void grpc2ros<{ros_type}, {proto_type}>(const {proto_type}& proto_msg, {ros_type}& ros_msg) {"{"}\n')
            for field_name, field_type, is_repeated in basic_fields:
                if is_repeated:
                    f.write(
                        f'    carefulResize(ros_msg.{field_name}, proto_msg.{field_name}_size());\n'
                        f'    std::copy(proto_msg.{field_name}().begin(), proto_msg.{field_name}().end(), ros_msg.{field_name}.begin());\n')
                else:
                    f.write(f'    ros_msg.{field_name} = proto_msg.{field_name}();\n')

            for field_name, field_type, is_repeated in message_files:
                if field_name == '__ros_bridge_grpc_empty_msg': continue
                if is_repeated:
                    f.write(
                        f'    carefulResize(ros_msg.{field_name}, proto_msg.{field_name}_size());\n'
                        f'    for (std::size_t idx = 0; idx < proto_msg.{field_name}_size(); idx++) {"{"}\n'
                        f'        grpc2ros(proto_msg.{field_name}(idx), ros_msg.{field_name}.at(idx));\n'
                        f'    {"}"}\n'
                    )
                else:
                    f.write(f'    grpc2ros(proto_msg.{field_name}(), ros_msg.{field_name});\n')
            f.write("}\n\n")


def generate_registration_functions(file_metadata: FileMetadata, dest_path: str):
    ros_type = file_metadata.ros_type
    msg_package = file_metadata.msg_package
    msg_class = file_metadata.msg_class
    msg_type = file_metadata.msg_type
    mode = file_metadata.mode
    proto_type = file_metadata.proto_type
    ros_header = file_metadata.header

    with open(os.path.join(dest_path, 'bridge_types.hpp'), 'a') as bridge_file:
        bridge_file.write(
            f'#include <{msg_package}.{msg_class}.{msg_type}.pb.h>\n'
            f'#include <{ros_header}>\n'
        )

        for proto_type, ros_type in zip(file_metadata.proto_type, file_metadata.ros_type):
            bridge_file.write(
                f'void grpc2ros(const {proto_type}&, {ros_type}&);\n'
                f'void ros2grpc(const {ros_type}&, {proto_type}&);\n'
            )

    with open(os.path.join(dest_path, 'register_types.hpp'), 'a') as register_file:
        if msg_class == 'msg':
            register_file.write(
                f'BridgeServerROS{mode[-1]}::subscriber_registration_callbacks["{msg_package}/msg/{msg_type}"] = registerSubscription<{ros_type}>;\n'
                f'BridgeServerROS{mode[-1]}::publisher_registration_callbacks["{msg_package}/msg/{msg_type}"] = registerPublisher<{ros_type}>;\n'
            )

        elif msg_class == 'srv':
            service_type = file_metadata.service_type
            register_file.write(
                f'BridgeServerROS{mode[-1]}::client_registration_callbacks["{msg_package}/srv/{msg_type}"] = registerServiceClient<{service_type}>;\n'
                f'BridgeServerROS{mode[-1]}::server_registration_callbacks["{msg_package}/srv/{msg_type}"] = registerServiceServer<{service_type}>;\n'
            )

def main():
    if len(sys.argv) < 2:
        print('Missing required positional argument code generation path')
        exit(1)

    gen_path = sys.argv[1]

    if not os.path.exists(os.path.join(gen_path, 'conversions')):
        os.mkdir(os.path.join(gen_path, 'conversions'))

    for mode in ['ros1', 'ros2']:
        dest_path = os.path.join(gen_path, 'conversions', mode)
        if not os.path.exists(dest_path):
            os.mkdir(dest_path)
        
        # Clear the final bridge_types.hpp and register_types.hpp file
        with open(os.path.join(dest_path, 'bridge_types.hpp'), 'w'):
            pass
        with open(os.path.join(dest_path, 'register_types.hpp'), 'w'):
            pass

        proto_path = os.path.join(gen_path, 'proto')
        for file_path in Path(proto_path).rglob('*.proto'):
            file_metadata = FileMetadata(file_path, mode)
            generate_cpp_conversion_code(file_metadata, dest_path)
            generate_registration_functions(file_metadata, dest_path)

            if file_metadata.msg_class == 'msg':
                add_publisher_generator_callback(file_metadata, dest_path)
                add_subscription_generator_callback(file_metadata, dest_path)

            elif file_metadata.msg_class == 'srv':
                add_client_generator_callback(file_metadata, dest_path)
                add_service_generator_callback(file_metadata, dest_path)

if __name__ == '__main__':
    main()