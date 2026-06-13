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

def check_constant_compatibility(message_obj, proto_comment: Comment, override: bool, logger: Logger) -> bool:
    """
    Checks whether a constant defined in a proto file has the same value as the 
    consant in the ROS1 message. Constants are encoded into proto files as comments
    of the form "// ConstantName = value;"
    """

    # Ignore the line signalling that we are listing constants
    text = proto_comment.text[3:].strip()
    if text == 'Constants':
        return True

    msg_package, msg_name = message_obj._type.split('/')

    # Make sure the constant is present in both definitions
    name, value = text.split(' = ')
    value = value[:-1] # remove semicolon
    if not hasattr(message_obj, name):
        logger.log_msg(f'{msg_package}/{msg_name} has constant {name} in ROS2 but not in ROS1')
        if override:
            logger.log_msg(f'Allowing via user override')
            return True
        else:
            return False

    # Make sure the constant value is the same in both definitions
    ros1_constant_value = getattr(message_obj, name)
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
    
    return True

def check_packet_compatibility(message_obj, proto_field: Field, fields_to_delete: set, matched_fields: list, override: bool, logger: Logger) -> bool:
    """
    For a given Python message type, check all the lines of the protobuf packet struct
    match the definition of the type. This checks for type equality, cardinality (i.e.
    optional, repeated, etc.) and size if applicable. Also checks all constants defined
    in the message to make sure that they match between versions as well
    """
    # TODO: Check repeated size

    msg_package, msg_name = message_obj._type.split('/')

    if proto_field.name not in message_obj.__slots__:
        logger.log_msg(f'Message type {msg_package}/{msg_name} has field {proto_field.name} in ROS2 but not in ROS1')
        if override:
            fields_to_delete.add(proto_field.name)
            return True
        else:
            return False

    corresponding_field_idx = message_obj.__slots__.index(proto_field.name)
    ros1_msg_type: str = message_obj._slot_types[corresponding_field_idx]
    ros2_msg_type: str = proto_field.type.replace('_proto.', '.').replace('.', '/')

    # We cannot reconcile (and therefore override) a cardinality mismatch
    if ros1_msg_type.endswith(']'):
        if proto_field.cardinality != FieldCardinality.REPEATED and proto_field.type != 'bytes':
            logger.log_msg(f'{msg_package}/{proto_field.name} is an array in ROS1 but not in ROS2')
            return False
        ros1_msg_type = ros1_msg_type[:ros1_msg_type.find('[')]

    if not are_types_equivalent(ros1_msg_type, ros2_msg_type):
        logger.log_msg(f'Message type {msg_package}/{proto_field.name} has type {ros2_msg_type} in ROS2 but type {ros1_msg_type} in ROS1')
        if override:
            fields_to_delete.add(proto_field.name)
            return True
        else:
            return False

    matched_fields.append(proto_field.name)
    return True

def write_corrected_field(message_obj, message_lines: list, file_handle, fields_to_delete: set, logger: Logger) -> None:
    """
    Given that a particular message type was overridden and had incompatibilities,
    rewrite the file with only the fields that are shared between the two message
    types.
    """
    
    msg_package, msg_name = message_obj._type.split('/')

    if fields_to_delete:
        logger.log_msg(f'{msg_package}/{msg_name} comptibility overriden by ignoring fields:')
        [logger.log_msg(f'\t{name}') for name in fields_to_delete]

    lines_to_keep = []
    for line in message_lines:
        # Skip lines that do not define fields
        if not line.strip().endswith(';'):
            lines_to_keep.append(line)
            continue

        # Check if the line contains an incompatible field
        field_name = line.strip().split(' ')[-3]
        if field_name in fields_to_delete:
            continue

        lines_to_keep.append(line)

    file_handle.writelines(lines_to_keep)

def split_proto_text(lines: list) -> list:
    """
    Given a sequence of lines from a proto file, extract and separate out all sections
    into individual lists of lines
    """
    field_started = False
    header_lines = []
    message_lines = []
    service_lines = []

    line: str
    messages_started = False
    for line in lines:
        if line.startswith('message'):
            field_started = True
            messages_started = True
            message_lines.append([])
            message: list = message_lines[-1]

        if not messages_started:
            header_lines.append(line)
        elif messages_started and not field_started:
            service_lines.append(line)
        elif field_started:
            message.append(line)
            if line.startswith('}'):
                field_started = False
                message = None

    return header_lines, message_lines, service_lines

def check_interface_compatibility(msg_package: str, msg_class: str, msg_name: str, proto_filepath: str, msg_overrides: list, logger: Logger) -> bool:
    # If there are incompatibilities, then we have to delete the offending fields.
    # In that case, they will be omitted from the bridge and always have default values
    is_overriden: bool = f'{msg_package}/{msg_class}/{msg_name}' in msg_overrides

    # Read the proto file
    try:
        with open(proto_filepath, 'r') as f:
            file_text: str = f.readlines()
            proto_data = Parser().parse('\n'.join(file_text))
    except FileNotFoundError:
        logger.log_msg(f'File {proto_filepath} seems to not exist')
        return False
    
    # Extract the text of the message section of the proto file
    header, messages, service = split_proto_text(file_text)
    
    # Import the corresponding ROS message package
    if msg_package not in loaded_msg_packages:
        try:
            loaded_msg_packages[msg_package] = importlib.import_module(f'{msg_package}.{msg_class}')
        except ModuleNotFoundError:
            logger.log_msg(f'Unable to import {msg_package}.msg')
            return False

    # Ensure that the message package contains the message type as well
    if not hasattr(loaded_msg_packages[msg_package], msg_name):
        logger.log_msg(f'Package {msg_package}/{msg_class} does not contain the interface type {msg_name}')
        return False
    ros_msg_class = getattr(loaded_msg_packages[msg_package], msg_name)

    # Extract the ROS message section of the proto message
    matched_fields = []
    message_elements = []
    for element in proto_data.file_elements:
        if isinstance(element, Message):
            message_elements.append(element)
    
    # Take only the ROS message definitions, not our packet definitions
    if msg_class == 'msg':
        message_elements = [message_elements[0]]
    elif msg_class == 'srv':
        message_elements = message_elements[0:2]

    # Rewrite the file, making any adjustments needed along the way
    with open(proto_filepath, 'w') as f:
        f.writelines(header)

        # Check each message field in the proto message to ensure that it is compatible with a corresponding field in the ROS message
        for message_element, message_text in zip(message_elements, messages):
            fields_to_delete = set()

            if msg_class == 'srv' and message_element.name.endswith('Request'):
                ros_msg_obj = ros_msg_class._request_class
            elif msg_class == 'srv' and message_element.name.endswith('Response'):
                ros_msg_obj = ros_msg_class._response_class
            elif msg_class == 'msg':
                ros_msg_obj = ros_msg_class

            for proto_field in message_element.elements:
                # Constant values are stored in the comments
                if isinstance(proto_field, Comment):
                    if not check_constant_compatibility(ros_msg_obj, proto_field, is_overriden, logger):
                        return False

                # We check if each field has the same name, type, cardinality (optional, repeated, etc.), and size (if applicable)
                elif isinstance(proto_field, Field):
                    if not check_packet_compatibility(ros_msg_obj, proto_field, fields_to_delete, matched_fields, is_overriden, logger):
                        return False
                    
                else:
                    logger.log_msg(f'Unexpected field type received: {type(proto_field)}')
                    return False

            # Check for values that exist in ROS1 but not in ROS2
            for elem in ros_msg_obj.__slots__:
                if elem not in matched_fields and elem not in fields_to_delete:
                    logger.log_msg(f'{msg_package}/{msg_name} has field {elem} in ROS1 but not in ROS2')
                    if is_overriden:
                        fields_to_delete.add(elem)
                    else:
                        return False
                    
            write_corrected_field(ros_msg_class, message_text, f, fields_to_delete, logger)

        # Write the packet fields
        if msg_class == 'msg':
            f.writelines(messages[1])
        elif msg_class == 'srv':
            f.writelines(messages[2])
            f.writelines(messages[3])
        
        # Write the service lines to close out the file
        f.writelines(service)               

    return True

def get_all_known_message_types() -> Dict[str, List[str]]:
    rospack = rospkg.RosPack()

    # Create a lookup for all message types known in ROS1
    rosmsg_packages = rosmsg.iterate_packages(rospack, '.msg')
    message_lookup: dict[str, list[str]] = {}
    for package, _ in rosmsg_packages:
        message_lookup[package] = []
        for message_type in rosmsg.list_msgs(package, rospack):
            message_lookup[package].append(message_type[len(package)+1:])

    # Create a lookup for all service types known in ROS1
    rossrv_packages = rosmsg.iterate_packages(rospack, '.srv')
    service_lookup: dict[str, list[str]] = {}
    for package, _ in rossrv_packages:
        service_lookup[package] = []
        for message_type in rosmsg.list_srvs(package, rospack):
            service_lookup[package].append(message_type[len(package)+1:])

    return message_lookup, service_lookup

def main():
    if len(sys.argv) < 2:
        print("Missing required positional argument proto_path")
        exit(1)

    message_lookup, service_lookup = get_all_known_message_types()
    msg_overrides = os.getenv('COMPAT_OVERRIDES', '').split(' ')

    missed_packages = set()
    proto_path = sys.argv[1]
    logger = Logger(os.path.join(proto_path, 'log', 'ros1_bridge.txt'))
    for file_path in Path(proto_path).rglob('*.proto'):
        filename = os.path.basename(file_path)
        msg_package, msg_class, msg_typename = os.path.splitext(filename)[0].split('.')

        if msg_class == 'msg':
            lookup = message_lookup
        elif msg_class == 'srv':
            lookup = service_lookup
        else:
            logger.log_msg(f'Received unsupported interface type "{msg_class}"')
            missed_packages.add(msg_typename)
            continue
        
        if msg_package not in lookup or msg_typename not in lookup[msg_package]:
            missed_packages.add(msg_typename)
            logger.log_msg(f'Cannot find matching type {msg_typename} in package {msg_package}')
            logger.log_msg(f'Deleting {file_path}')
            os.remove(file_path)
            continue

        if not check_interface_compatibility(msg_package, msg_class, msg_typename, str(file_path), msg_overrides, logger):
            logger.log_msg(f'Message {msg_package}/{msg_typename} is not compatible between ROS1 and ROS2')
            logger.log_msg(f'Deleting {file_path}')
            os.remove(file_path)
            continue

    if len(missed_packages) > 0:
        logger.log_msg('Unable to find matching interfaces for:')
        for missed_package in sorted(missed_packages):
            logger.log_msg(f'\t{missed_package}')

if __name__ == "__main__":
    main()