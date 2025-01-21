import re
import os
import sys
from pathlib import Path
from proto_schema_parser import Parser, Message, FieldCardinality
from proto_schema_parser.ast import Field

ros_basic_types = ['bool', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64', 'float32', 'float64', 'string']

def to_snake(name: str) -> str:
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name).lower()

def parse_proto(proto_path: str):
    """ Parse a .proto file into a set of message names and types
        separated by builtin types and message types. Each type also 
        has a boolean flag indicating whether the field is a repeated
        field
    """
    with open(proto_path, 'r') as f:
        proto_data = Parser().parse(f.read())

    basic_fields = []
    message_fields = []
    for element in proto_data.file_elements:
        if not isinstance(element, Message): continue
        
        for proto_field in element.elements:
            if not isinstance(proto_field, Field): continue

            is_repeated = proto_field.cardinality == FieldCardinality.REPEATED
            if proto_field.type in ros_basic_types:
                basic_fields.append((proto_field.name, proto_field.type, is_repeated))
            else:
                message_fields.append((proto_field.name, proto_field.type, is_repeated))

        # We stop after the first message, which is the ROS message definition
        break

    return basic_fields, message_fields

def generate_cpp_conversion_code(msg_package: str, msg_type: str, basic_fields: list[str], message_fields: list[str], gen_path: str, mode: str = 'ros2') -> None:
    # class F:
    #     def write(self, str):
    #         print(str, end='')
    # f = F()
    filename = f'convert_{msg_package}_{msg_type}.hpp'
    proto_type = f'{msg_package}_proto::{msg_type}'

    if mode == 'ros1':
        ros_type = f'{msg_package}::{msg_type}'
        subscriber_string = subscriber_base_string = 'ros::Subscriber'
        publisher_string = 'ros::Publisher'
        node_string = 'ros::NodeHandle&'
        create_pub_string = 'nh.advertise'
        create_sub_string = 'nh.subscribe'
        info = 'ROS_INFO('
        header = f'{msg_package}/{msg_type}.h'

    elif mode == 'ros2':
        ros_type = f'{msg_package}::msg::{msg_type}'
        subscriber_string = f'rclcpp::Subscription<{msg_package}::{msg_type}>'
        subscriber_base_string = f'rclcpp::SubscriptionBase'
        publisher_string = f'rclcpp::Publisher<{msg_package}::{msg_type}>'
        node_string = 'rclcpp::Node::SharedPtr'
        create_pub_string = f'*nh->create_publisher<{msg_package}::{msg_type}>'
        create_sub_string = f'*nh->create_subscription<{msg_package}::{msg_type}>'
        info = 'RCLCPP_INFO(nh->get_logger(), '
        header = f'{msg_package}/msg/{to_snake(msg_type)}.hpp'

    with open(os.path.join(gen_path, filename), 'w') as f:
        # Headers
        f.write(
            f'#include <{msg_package}.{msg_type}.pb.h>\n'
            f'#include <{header}>\n'
            '\n'
        )

        # Add a function to convert this message type from ros to grpc
        f.write(f'void ros2grpc(const {ros_type}& ros_msg, {proto_type}& proto_msg) {"{"}\n')
        for field_name, field_type, is_repeated in basic_fields:
            if is_repeated:
                f.write(f'    proto_msg.mutable_{field_name}()->Assign(std::begin(ros_msg.{field_name}), std::end(ros_msg.{field_name}));\n')
            else:
                f.write(f'    proto_msg.set_{field_name}(ros_msg.{field_name});\n')
                
        for field_name, field_type, is_repeated in message_fields:
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
        f.write(f'void grpc2ros(const {proto_type}& proto_msg, {ros_type}& ros_msg) {"{"}\n')
        for field_name, field_type, is_repeated in basic_fields:
            if is_repeated:
                f.write(f'    ros_msg.{field_name}.assign(proto_msg.{field_name}().begin(), proto_msg.{field_name}.end());\n')
            else:
                f.write(f'    ros_msg.{field_name} = proto_msg.{field_name}();\n')

        for field_name, field_type, is_repeated in message_fields:
            if is_repeated:
                f.write(
                    f'    ros_msg.{field_name}.resize(proto_msg.{field_name}_size());\n'
                    f'    for (std::size_t idx = 0; idx < proto_msg.{field_name}_size(); idx++) {"{"}\n'
                    f'        grpc2ros(proto_msg.{field_name}(idx), ros_msg.{field_name}.at(idx));\n'
                    f'    {"}"}\n'
                )
            else:
                f.write(f'    grpc2ros(*proto_msg.{field_name}(), ros_msg.{field_name});\n')
        f.write("}\n\n")

        # Add function to create subscriber and a gRPC publisher
        f.write(
            f'template<>\n'
            f'std::shared_ptr<{subscriber_base_string}> registerSubscription<{ros_type}>(const std::string& topic, {node_string} nh, std::shared_ptr<grpc::Channel> channel) {"{"}\n'
            f'    static std::map<grpc::Channel*, std::unique_ptr<{msg_package}_proto::Send{msg_type}ROS::Stub>> stubs;\n'
            f'    if (!stubs.count(channel.get())) {"{"}\n'
            f'        stubs[channel.get()] = std::move({msg_package}_proto::Send{msg_type}ROS::NewStub(channel));\n'
            f'    {"}"}\n'
            f'    \n'
            f'    auto& stub = stubs.at(channel.get());\n'
            f'    auto callback = [&stub, topic](const {ros_type}::SharedPtr msg) {"{"}\n'
            f'        {proto_type}Packet proto_message;\n'
            f'        proto_message.set_topic(topic);\n'
            f'        ros2grpc(*msg, *proto_message.mutable_message());\n'
            f'        grpc::ClientContext client_context;\n'
            f'        google::protobuf::Empty empty_message;\n'
            f'        grpc::Status statuc = stub->SendROSMessage(&client_context, proto_message, empty_message);\n'
            f'        if (!status.ok()) {info}gRPC call failed sending message type {ros_type} across bridge);\n'
            f'    {"}"};\n'
            f'    \n'
            f'    auto sub = std::make_shared<{subscriber_string}>({create_sub_string}(topic, 10, callback));\n'
            f'    return std::static_pointer_cast<{subscriber_base_string}>(sub);\n'
            f'{"}"}\n\n'
        )
        
        # Add function to create publisher and a gRPC subscription
        f.write(
            f'template<>\n'
            f'std::any registerPublisher<{ros_type}>(const std::string& topic, {node_string} nh, grpc::ServerBuilder& server_builder) {"{"}\n'
            f'    class SendROSMessageImpl final : public {msg_package}_proto::Send{msg_type}ROS::Service {"{"}\n'
            f'    public:\n'
            f'        SendROSMessageImpl({node_string} node, const std::string& topic) {"{"} : \n'
            f'            pub_({create_pub_string}(topic, 10)) {"{}"}\n\n'
            f'        grpc::Status SendROSMessage (grpc::ServerContext* context, const {proto_type}Packet* message, google::protobuf::Empty* response) override {"{"}\n'
            f'            {ros_type} ros_msg;\n'
            f'            grpc2ros(message->message(), ros_msg);\n'
            f'            pub->publish(ros_msg);\n'
            f'            return grpc::Status::OK;\n'
            f'        {"}"}\n'
            f'    \n'
            f'    private:\n'      
            f'        std::shared_ptr<{publisher_string}> pub_;\n'
            f'    {"}"};\n'
            f'    std::any ros_pub_service = std::make_any<SendROSMessageImpl>(nh, topic);\n'
            f'    builder.RegisterService(std::any_cast<SendROSMessageImpl>(&ros_pub_service));\n'
            f'    return ros_pub_service;\n'
            f'{"}"};\n'
        )

        # Register the functions
        f.write('\n'
            f'const auto {msg_package}_{msg_type}_registration_success = std::invoke([]{"{"}\n'
            f'    BridgeServerROS{mode[-1]}::subscriber_registration_callbacks["{msg_package}/{msg_type}"] = registerSubscription<{ros_type}>;\n'
            f'    BridgeServerROS{mode[-1]}::publisher_registration_callbacks["{msg_package}/{msg_type}"] = registerPublisher<{ros_type}>;\n'
            f'    return true;\n'
            f'{"});"}\n'
        )

    with open(os.path.join(gen_path, 'bridge_types.hpp'), 'a') as bridge_file:
        bridge_file.write(f'#include "{filename}"\n')

def main():
    if len(sys.argv) < 2:
        print('Missing required positional argument code generation path')
        exit(1)

    gen_path = sys.argv[1]
    dest_path = os.path.join(gen_path, 'conversions')
    if not os.path.exists(dest_path):
        os.mkdir(dest_path)
    
    # Clear the final bridge_type.hpp file
    with open(os.path.join(dest_path, 'bridge_types.hpp'), 'w'):
        pass

    proto_path = os.path.join(gen_path, 'proto')
    for file_path in Path(proto_path).rglob('*.proto'):
        file_name = os.path.basename(file_path)
        msg_package, msg_type, _ = file_name.split('.')
        basic_fields, message_fields = parse_proto(file_path)
        generate_cpp_conversion_code(msg_package, msg_type, basic_fields, message_fields, dest_path, 'ros1')
        generate_cpp_conversion_code(msg_package, msg_type, basic_fields, message_fields, dest_path, 'ros2')

if __name__ == '__main__':
    main()