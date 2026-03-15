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

loaded_msg_packages = {}

compatible_types = {
    'float32': ['float', 'double'],
    'float64': ['float', 'double'],
    'uint8': ['uint32', 'bytes'],
    'uint16': ['uint32'],
    'int8': ['int32', 'bytes'],
    'int16': ['int32'],
    'byte': ['uint32', 'int32', 'bytes'],
    'time': ['google/protobuf/Timestamp'],
    'duration': ['google/protobuf/Duration'],
    'char': ['uint32', 'int32']
}

class Logger:
    def __init__(self, path: str):
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.file = open(path, 'w')

    def log_msg(self, msg: str):
        self.file.write(f'{msg}\n')
        print(msg)

def are_types_equivalent(ros1_msg_type: str, ros2_msg_type: str) -> bool:
    if ros1_msg_type == ros2_msg_type:
        return True
    
    if ros1_msg_type in compatible_types:
        return ros2_msg_type in compatible_types[ros1_msg_type]
    
    return False

def check_msg_compatibility(msg_package: str, msg_name: str, proto_filepath: str, msg_overrides: list, logger: Logger) -> bool:
    # If there are incompatibilities, then we have to delete the offending fields.
    # In that case, they will be omitted from the bridge and always have default values
    fields_to_delete = set()
    is_overriden: bool = f'{msg_package}/{msg_name}' in msg_overrides

    try:
        with open(proto_filepath, 'r') as f:
            proto_data = Parser().parse(f.read())
        
        if msg_package not in loaded_msg_packages:
            loaded_msg_packages[msg_package] = importlib.import_module(f'{msg_package}.msg')

        if not hasattr(loaded_msg_packages[msg_package], msg_name):
            logger.log_msg(f'Package {msg_package} does not contain the message type {msg_name}')
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
                        logger.log_msg(f'{msg_package}/{msg_name} has constant {name} in ROS2 but not in ROS1')
                        if is_overriden:
                            continue
                        else:
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
                        logger.log_msg(f'{msg_package}/{msg_name} constant {name} has value {value} in ROS2 but value {ros1_constant_value} in ROS1')
                        return False

                # We check if each field has the same name, type, cardinality (optional, repeated, etc.), and size (if applicable)
                elif isinstance(proto_field, Field):
                    if proto_field.name not in ros_msg_class.__slots__:
                        logger.log_msg(f'Message type {msg_package}/{msg_name} has field {proto_field.name} in ROS2 but not in ROS1')
                        if is_overriden:
                            fields_to_delete.add(proto_field.name)
                            continue
                        else:
                            return False
                    
                    corresponding_field_idx = ros_msg_class.__slots__.index(proto_field.name)
                    ros1_msg_type: str = ros_msg_class._slot_types[corresponding_field_idx]
                    ros2_msg_type: str = proto_field.type.replace('_proto.', '.').replace('.', '/')

                    # We cannot reconcile (and therefore override) a cardinality mismatch
                    if ros1_msg_type.endswith(']'):
                        if proto_field.cardinality != FieldCardinality.REPEATED and proto_field.type != 'bytes':
                            logger.log_msg(f'{msg_package}/{ros1_msg_type}:{proto_field.name} is an array in ROS1 but not in ROS2')
                            return False
                        ros1_msg_type = ros1_msg_type[:ros1_msg_type.find('[')]

                    if not are_types_equivalent(ros1_msg_type, ros2_msg_type):
                        logger.log_msg(f'Message type {msg_package}/{ros1_msg_type}:{proto_field.name} has type {ros2_msg_type} in ROS2 but type {ros1_msg_type} in ROS1')
                        if is_overriden:
                            fields_to_delete.add(proto_field.name)
                            continue
                        else:
                            return False
                    
                    matched_fields.append(proto_field.name)
                    
                else:
                    logger.log_msg(f'Unexpected field type received: {type(proto_field)}')

        # Check for values in ROS1 but not in ROS2
        for elem in ros_msg_class.__slots__:
            if elem not in matched_fields:
                logger.log_msg(f'{msg_package}/{msg_name} has field {elem} in ROS1 but not in ROS2')
                if is_overriden:
                    fields_to_delete.add(elem)
                else:
                    return False
        
    except FileNotFoundError:
        logger.log_msg(f'File {proto_filepath} seems to not exist')
        return False
    except ModuleNotFoundError:
        logger.log_msg(f'Unable to import {msg_package}.msg')
        return False
    
    # If requested, reconcile incompatibilties now by deleting the lines with the offending fields
    if is_overriden and len(fields_to_delete) > 0:
        logger.log_msg(f'{msg_package}/{msg_name} comptibility overriden by ignoring fields:')
        [logger.log_msg(f'\t{name}') for name in fields_to_delete]
        lines_to_keep = []
        with open(proto_filepath, 'r') as file:
            file_lines = file.readlines()

        done = False
        for line in file_lines:
            # The message definition comes first, so we can stop after the first close-brace
            if '}' in line:
                done = True

            if done:
                lines_to_keep.append(line)
                continue

            # Skip lines that do not define fields
            if not line.strip().endswith(';'):
                lines_to_keep.append(line)
                continue

            # Check if the line contains an incompatible field
            field_name = line.strip().split(' ')[1]
            if field_name in fields_to_delete:
                continue

            lines_to_keep.append(line)

        with open(proto_filepath, 'w') as file:
            file.writelines(lines_to_keep)

    return True

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
    msg_overrides = os.getenv('COMPAT_OVERRIDES', '').split(' ')

    missed_packages = set()
    proto_path = sys.argv[1]
    logger = Logger(os.path.join(proto_path, 'log', 'ros1_bridge.txt'))
    for file_path in Path(proto_path).rglob('*.proto'):
        filename = os.path.basename(file_path)
        msg_package, msg_typename = os.path.splitext(filename)[0].split('.')
        
        if msg_package not in message_lookup or msg_typename not in message_lookup[msg_package]:
            missed_packages.add(msg_typename)
            logger.log_msg(f'Cannot find matching type {msg_typename} in package {msg_package}')
            logger.log_msg(f'Deleting {file_path}')
            os.remove(file_path)
            continue

        if not check_msg_compatibility(msg_package, msg_typename, str(file_path), msg_overrides, logger):
            logger.log_msg(f'Message {msg_package}/{msg_typename} is not compatible between ROS1 and ROS2')
            logger.log_msg(f'Deleting {file_path}')
            os.remove(file_path)
            continue

    if len(missed_packages) > 0:
        logger.log_msg('Unable to find matching messages for:')
        for missed_package in sorted(missed_packages):
            logger.log_msg(f'\t{missed_package}')

if __name__ == "__main__":
    main()