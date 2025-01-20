import os
import re
import sys
import ast
import rosmsg
import rospkg
import importlib
from visualization_msgs.msg import Marker
from pathlib import Path
from typing import Dict, List
from proto_schema_parser import Parser, Message, FieldCardinality
from proto_schema_parser.ast import Comment, Field

import rospy

loaded_msg_packages = {}

compatible_types = {
    'float32': ['float', 'double'],
    'float64': ['float', 'double'],
    'uint8': ['uint32'],
    'uint16': ['uint32'],
    'int8': ['int32'],
    'int16': ['int32'],
    'byte': ['uint32', 'int32'],
    'time': ['google/protobuf/Timestamp'],
    'duration': ['google/protobuf/Duration'],
    'char': ['uint32', 'int32']
}

ros_basic_types = ['bool', 'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64', 'float32', 'float64', 'string']

def are_types_equivalent(ros1_msg_type: str, ros2_msg_type: str) -> bool:
    if ros1_msg_type == ros2_msg_type:
        return True
    
    if ros1_msg_type in compatible_types:
        return ros2_msg_type in compatible_types[ros1_msg_type]
    
    return False

def to_snake(name: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

def check_msg_compatibility(msg_package: str, msg_name: str, proto_filepath: str) -> bool:
    try:
        with open(proto_filepath, 'r') as f:
            proto_data = Parser().parse(f.read())
        
        if msg_package not in loaded_msg_packages:
            loaded_msg_packages[msg_package] = importlib.import_module(f'{msg_package}.msg')

        if not hasattr(loaded_msg_packages[msg_package], msg_name):
            print(f'Package {msg_package} does not contain the message type {msg_name}')
            return False
        ros_msg_class = getattr(loaded_msg_packages[msg_package], msg_name)

        # TODO: Check repeated size
        matched_fields = []
        for element in proto_data.file_elements:
            if not isinstance(element, Message): continue
            if element.name == f'{msg_name}Packet': continue

            for proto_field in element.elements:
                # Constant values are stored in the comments
                # For now we store these away to check later
                if isinstance(proto_field, Comment):
                    text = proto_field.text[3:].strip()
                    if text == 'Constants':
                        continue

                    # Make sure the constant is present in both definitions
                    name, value = text.split(' = ')
                    value = value[:-1] # remove semicolon
                    if not hasattr(ros_msg_class, name):
                        print(f'{msg_package}/{msg_name} has constant {name} in ROS2 but not in ROS1')
                        return False

                    # Make sure the constant value is the same in both definitions
                    ros1_constant_value = getattr(ros_msg_class, name)
                    is_numeric = is_bytes = False
                    equivalent_constant = True

                    # First try to convert the value string to a number, works for ints and floats
                    try:
                        float_val = float(value)
                        is_numeric = True
                        if float_val != ros1_constant_value:
                            equivalent_constant = False
                    except ValueError:
                        pass

                    # Value is not numeric - could still be bytes or string
                    try:
                        bytes_value = int.from_bytes(ast.literal_eval(value), byteorder='little')
                        is_bytes = True
                        if not is_numeric and bytes_value != ros1_constant_value:
                            equivalent_constant = False
                    except (TypeError, ValueError, SyntaxError):
                        pass

                    # Value is not a 'bytes' - treat as a string constant
                    if (not is_numeric) and (not is_bytes) and (value != str(ros1_constant_value)):
                        equivalent_constant = False
                        
                    if not equivalent_constant:
                        print(f'{msg_package}/{msg_name} constant {name} has value {value} in ROS2 but value {ros1_constant_value} in ROS1')
                        return False

                # We check if each field has the same name, type, cardinality (optional, repeated, etc.), and size (if applicable)
                elif isinstance(proto_field, Field):
                    if proto_field.name not in ros_msg_class.__slots__:
                        print(f'Message type {msg_package}/{msg_name} has field {proto_field.name} in ROS2 but not in ROS1')
                        return False
                    
                    corresponding_field_idx = ros_msg_class.__slots__.index(proto_field.name)
                    ros1_msg_type: str = ros_msg_class._slot_types[corresponding_field_idx]
                    ros2_msg_type: str = proto_field.type.replace('_proto.', '.').replace('.', '/')

                    if ros1_msg_type.endswith(']'):
                        if proto_field.cardinality != FieldCardinality.REPEATED:
                            print(f'{msg_package}/{ros1_msg_type}:{proto_field.name} is an array in ROS1 but not in ROS2')
                        ros1_msg_type = ros1_msg_type[:ros1_msg_type.find('[')]

                    if not are_types_equivalent(ros1_msg_type, ros2_msg_type):
                        print(f'Message type {msg_package}/{ros1_msg_type}:{proto_field.name} has type {ros2_msg_type} in ROS2 but type {ros1_msg_type} in ROS1')
                        return False
                    
                    matched_fields.append(proto_field.name)
                    
                else:
                    print(f'Unexpected field type received: {type(proto_field)}')

        # Check for values in ROS1 but not in ROS2
        for elem in ros_msg_class.__slots__:
            if elem not in matched_fields:
                print(f'{msg_package}/{msg_name} has field {elem} in ROS1 but not in ROS2')
                return False              
        
    except FileNotFoundError:
        print(f'File {proto_filepath} seems to not exist')
        return False
    except ModuleNotFoundError:
        print(f'Unable to import {msg_package}.msg')
        return False        
    
    return True

def generate_cpp_conversion_code(msg_package: str, msg_type: str, message_class, mode = 'ros2') -> None:
    class F:
        def write(self, str):
            print(str, end='')
    # with open("my_file") as f:
    f = F()

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

    # Headers
    f.write(
        f'#include <{msg_package}.{msg_type}.pb.h>\n'
        f'#include <{header}>\n'
        '\n'
    )

    # Add a function to convert this message type from ros to grpc
    f.write(f'void ros2grpc(const {ros_type}& ros_msg, {proto_type}& proto_msg) {"{"}\n')
    for field_idx, field_name in enumerate(message_class.__slots__):
        field_type: str = message_class._slot_types[field_idx]
        if field_type in ros_basic_types:
            f.write(f'        proto_message.set_{field_name}(ros_msg->{field_name});\n')
        else:
            f.write(f'        ros2grpc(ros_msg->{field_name}, *proto_message.mutable_{field_name}());\n')
    f.write("}\n\n")

    # Add a function to convert this message type from ros to grpc
    f.write(f'void grpc2ros(const {proto_type}& proto_msg, {ros_type}& ros_msg) {"{"}\n')
    for field_idx, field_name in enumerate(message_class.__slots__):
        field_type: str = message_class._slot_types[field_idx]
        if field_type in ros_basic_types:
            # f.write(f'        proto_message.set_{field_name}(ros_msg->{field_name});\n')
            f.write(f'        ros_msg->{field_name} = proto_message.{field_name}();\n')
        else:
            f.write(f'        grpc2ros(*proto_message.{field_name}(), ros_msg->{field_name});\n')
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

    print('\n')

def get_all_known_message_types() -> Dict[str, List[str]]:
    rospack = rospkg.RosPack()
    rosmsg_packages = rosmsg.iterate_packages(rospack, '.msg')

    # Create a lookup for all message types known in ROS1
    message_lookup: dict[str, list[str]] = {}
    for package, _ in rosmsg_packages:
        message_lookup[package] = []
        for message_type in rosmsg.list_msgs(package, rospack):
            message_lookup[package].append(message_type[len(package)+1:])

    return message_lookup

def main():
    if len(sys.argv) < 2:
        print("Missing required positional argument proto_path")
        exit(1)

    message_lookup = get_all_known_message_types()

    missed_packages = set()
    proto_path = sys.argv[1]
    for file_path in Path(proto_path).rglob('*.proto'):
        filename = os.path.basename(file_path)
        msg_package, msg_typename = os.path.splitext(filename)[0].split('.')

        if msg_package not in message_lookup:
            missed_packages.add(msg_package)
            continue
        
        if msg_typename not in message_lookup[msg_package]:
            print(f'Cannot find matching type {msg_typename} in package {msg_package}')
            continue

        if not check_msg_compatibility(msg_package, msg_typename, file_path):
            # print(f'Message {msg_package}/{msg_typename} is not compatible between ROS1 and ROS2')
            continue

        generate_cpp_conversion_code(msg_package, msg_typename, getattr(loaded_msg_packages[msg_package], msg_typename))

    print('Unable to find matching packages for:')
    for missed_packge in sorted(missed_packages):
        print('\t', missed_packge)

if __name__ == "__main__":
    main()