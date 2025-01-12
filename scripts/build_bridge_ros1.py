import os
import sys
import rosmsg
import rospkg
import importlib
from visualization_msgs.msg import Marker
from pathlib import Path
from typing import Dict, List
from proto_schema_parser import Parser, Message, FieldCardinality
from proto_schema_parser.ast import Comment, Field

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

def are_types_equivalent(ros1_msg_type: str, ros2_msg_type: str) -> bool:
    if ros1_msg_type == ros2_msg_type:
        return True
    
    if ros1_msg_type in compatible_types:
        return ros2_msg_type in compatible_types[ros1_msg_type]
    
    return False

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
        has_constants = False
        constants = {}
        for element in proto_data.file_elements:
            if not isinstance(element, Message): continue
            for proto_field in element.elements:
                # Constant values are stored in the comments
                # For now we store these away to check later
                if isinstance(proto_field, Comment):
                    text = proto_field.text[3:].strip()
                    if text == 'Constants':
                        has_constants = True
                    else:
                        name, val = text.split(' = ')
                        constants[name] = val[:-1]
                    continue

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
                    
                else:
                    print(f'Unexpected field type received: {type(proto_field)}')
                
        if has_constants:
            for name, value in constants.items():
                if not hasattr(ros_msg_class, name):
                    print(f'{msg_package}/{ros1_msg_type} has constant {name} in ROS2 but not in ROS1')

                try:
                    ros1_constant_value = getattr(ros_msg_class, name)
                    if float(value) != ros1_constant_value:
                        print(f'{msg_package}/{ros1_msg_type} constant {name} has value {value} in ROS2 but value {ros1_constant_value} in ROS1')
                except:
                    if value != str(ros1_constant_value):
                        print(f'{msg_package}/{ros1_msg_type} constant {name} has value {value} in ROS2 but value {ros1_constant_value} in ROS1')

            print(f'{msg_package}/{msg_name} consants matched')
                
        
    except FileNotFoundError:
        print(f'File {proto_filepath} seems to not exist')
        return False
    except ModuleNotFoundError:
        print(f'Unable to import {msg_package}.msg')
        return False        
    
    return True

def generate_cpp_conversion_code(msg_package: str, msg_type: str) -> None:
    class F:
        def write(self, str):
            print(str)
    # with open("my_file") as f:
    f = F()
    f.write(
        f'#include <{msg_package}.{msg_type}.pb.h>\n'
        f'#include <{msg_package}/{msg_type}.h\n'
        '\n'
        
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

        # generate_cpp_conversion_code(msg_package, msg_typename)

    print('Unable to find matching packages for:')
    for missed_packge in missed_packages:
        print('\t', missed_packge)

if __name__ == "__main__":
    main()