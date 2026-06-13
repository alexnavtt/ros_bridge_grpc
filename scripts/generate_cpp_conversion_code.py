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

        # Define what the C++ types are called in this ROS version for this message/service type
        if self.mode == 'ros1':
            self.ros_type = f'{self.msg_package}::{self.msg_type}' # eg. std_msgs::String or std_srvs::SetBool
            self.header = f'{self.msg_package}/{self.msg_type}.h'  # eg. std_msgs/String.h or std_srvs/SetBool.h
            self.pointer = 'ConstPtr'                              # eg. std_msgs::String::ConstPtr

        elif self.mode == 'ros2':
            self.ros_type = f'{self.msg_package}::{self.msg_class}::{self.msg_type}'            # eg. std_msgs::msg::String or std_srvs::srv::SetBool
            self.header = f'{self.msg_package}/{self.msg_class}/{to_snake(self.msg_type)}.hpp'  # eg. std_msgs/msg/string.hpp or std_srvs/srv/set_bool.hpp
            self.pointer = 'ConstSharedPtr'                                                     # eg. std_msgs::msg::String::ConstSharedPtr

        if self.msg_class == 'msg':
            self.ros_type = [self.ros_type]
            self.proto_type = [f'{self.msg_package}_{self.msg_class}_proto::{self.msg_type}']
        elif self.msg_class == 'srv':
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

def add_subscription_generator_callback(file_metadata: FileMetadata, f: typing.IO) -> None:
    ros_type = file_metadata.ros_type
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    pointer = file_metadata.pointer
    mode = file_metadata.mode
    proto_type = file_metadata.proto_type
    
    f.write(
        f'template<>\n'
        f'std::shared_ptr<SUBSCRIBER_BASE> registerSubscription<{ros_type}>(const std::string& topic, NODE nh, std::shared_ptr<grpc::Channel> channel, [[maybe_unused]] bool transient_local, [[maybe_unused]] bool best_effort) {"{"}\n'
        f'    static std::map<grpc::Channel*, std::unique_ptr<{msg_package}_proto::Send{msg_type}ROS::Stub>> stubs;\n'
        f'    if (!stubs.count(channel.get())) {"{"}\n'
        f'        stubs[channel.get()] = std::move({msg_package}_proto::Send{msg_type}ROS::NewStub(channel));\n'
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
        f'        client_context.AddMetadata("{mode}", "");\n'
        f'        grpc::Status status = stub->SendROSMessage(&client_context, proto_message, &empty_message);\n'
        f'        if (!status.ok()) LOG_INFO(nh, "gRPC call failed sending message type {ros_type} across bridge");\n'
        f'    {"}"};\n'
        f'    \n'
        f'    auto sub = CREATE_SUB_POINTER(nh, {ros_type}, topic, callback, transient_local, best_effort);\n'
        f'    return std::static_pointer_cast<SUBSCRIBER_BASE>(sub);\n'
        f'{"}"}\n\n'
    )

def add_publisher_generator_callback(file_metadata: FileMetadata, f: typing.IO) -> None:
    ros_type = file_metadata.ros_type
    msg_package = file_metadata.msg_package
    msg_type = file_metadata.msg_type
    mode = file_metadata.mode
    proto_type = file_metadata.proto_type

    f.write(
        f'template<>\n'
        f'std::shared_ptr<grpc::Service> registerPublisher<{ros_type}>(const std::string& topic, NODE nh, grpc::ServerBuilder& server_builder, bool transient_local, bool best_effort) {"{"}\n'
        f'    class SendROSMessageImpl final : public {msg_package}_proto::Send{msg_type}ROS::Service {"{"}\n'
        f'    public:\n'
        f'        grpc::Status SendROSMessage (grpc::ServerContext* context, const {proto_type}Packet* message, google::protobuf::Empty* response) override {"{"}\n'
        f'            if (context->client_metadata().count("{mode}")) return grpc::Status::OK;\n'
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
        f'{"}"};\n'
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

    if msg_class == 'msg':
        with open(os.path.join(dest_path, 'bridge_types.hpp'), 'a') as bridge_file:
            bridge_file.write(
                f'#include <{msg_package}.{msg_class}.{msg_type}.pb.h>\n'
                f'#include <{ros_header}>\n'
                f'void grpc2ros(const {proto_type}&, {ros_type}&);\n'
                f'void ros2grpc(const {ros_type}&, {proto_type}&);\n'
            )

        with open(os.path.join(dest_path, 'register_types.hpp'), 'a') as register_file:
            register_file.write(
                f'BridgeServerROS{mode[-1]}::subscriber_registration_callbacks["{msg_package}/msg/{msg_type}"] = registerSubscription<{ros_type}>;\n'
                f'BridgeServerROS{mode[-1]}::publisher_registration_callbacks["{msg_package}/msg/{msg_type}"] = registerPublisher<{ros_type}>;\n'
            )

    elif msg_class == 'srv':
        with open(os.path.join(dest_path, 'bridge_types.hpp'), 'a') as bridge_file:
            bridge_file.write(
                f'#include <{msg_package}.{msg_class}.{msg_type}.pb.h>\n'
                f'#include <{ros_header}>\n'
                f'void grpc2ros(const {proto_type}Request&, {ros_type}::Request&);\n'
                f'void grpc2ros(const {proto_type}Response&, {ros_type}::Response&);\n'
                f'void ros2grpc(const {ros_type}::Request&, {proto_type}Request&);\n'
                f'void ros2grpc(const {ros_type}::Response&, {proto_type}Response&);\n'
            )

        with open(os.path.join(dest_path, 'register_types.hpp'), 'a') as register_file:
            register_file.write(
                f'BridgeServerROS{mode[-1]}::client_registration_callbacks["{msg_package}/srv/{msg_type}"] = registerClient<{ros_type}>;\n'
                f'BridgeServerROS{mode[-1]}::server_registration_callbacks["{msg_package}/srv/{msg_type}"] = registerServer<{ros_type}>;\n'
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

if __name__ == '__main__':
    main()