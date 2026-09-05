import os
import ast
import argparse
import importlib
from pathlib import Path
from typing import Dict, List
from proto_schema_parser import Parser, Message, FieldCardinality
from proto_schema_parser.ast import Comment, Field

loaded_msg_packages = {}
sideA: str # ROS2 distro
sideB: str # Other ROS2 distro or ROS1 noetic

compatible_types = {
    'float32': ['float', 'double'],
    'float64': ['float', 'double'],
    'uint8': ['uint32', 'bytes'],
    'uint16': ['uint32'],
    'int8': ['int32', 'bytes'],
    'int16': ['int32'],
    'byte': ['uint32', 'int32', 'bytes'],
    'octet': ['uint32', 'int32', 'bytes'],
    'time': ['google/protobuf/Timestamp'],
    'duration': ['google/protobuf/Duration'],
    'char': ['uint32', 'int32'],
    'boolean': ['bool'],
    'builtin_interfaces/Time': ['google/protobuf/Timestamp'],
    'builtin_interfaces/Duration': ['google/protobuf/Duration']
}

class Logger:
    def __init__(self, path: str):
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.file = open(path, 'w')

    def log_msg(self, msg: str):
        self.file.write(f'{msg}\n')
        print(msg)

def are_types_equivalent(ros_msg_type: str, proto_msg_type: str) -> bool:
    if ros_msg_type == proto_msg_type:
        return True
    
    if ros_msg_type in compatible_types:
        return proto_msg_type in compatible_types[ros_msg_type]
    
    return False

def check_constant_compatibility(message_obj, proto_comment: Comment, override: bool, logger: Logger) -> bool:
    """
    Checks whether a constant defined in a proto file has the same value as the 
    consant in the current ROS message version. Constants are encoded into proto files
    as comments of the form "// ConstantName = value;"
    """

    # Ignore the line signalling that we are listing constants
    text = proto_comment.text[3:].strip()
    if text == 'Constants':
        return True

    msg_package = message_obj.__module__.split('.')[0]
    msg_name = message_obj.__name__

    # Make sure the constant is present in both definitions
    name, value = text.split(' = ')
    value = value[:-1] # remove semicolon
    if not hasattr(message_obj, name):
        logger.log_msg(f'{msg_package}/{msg_name} has constant {name} in {sideA} but not in {sideB}')
        if override:
            logger.log_msg(f'Allowing via user override')
            return True
        else:
            return False

    # Make sure the constant value is the same in both definitions
    sideB_constant_value = getattr(message_obj, name)
    is_numeric = is_bytes = False
    equivalent_constant = True

    # First try to convert the value string to a number, works for ints and floats
    try:
        float_val = float(value)
        is_numeric = True
        if float_val != sideB_constant_value:
            equivalent_constant = False
    except ValueError:
        pass

    # Value is not numeric - could still be bytes or string
    try:
        bytes_value = int.from_bytes(ast.literal_eval(value), byteorder='little')
        is_bytes = True
        if not is_numeric and bytes_value != sideB_constant_value and bytes_value != int.from_bytes(sideB_constant_value):
            equivalent_constant = False
    except (TypeError, ValueError, SyntaxError):
        pass

    # Value is not a 'bytes' - treat as a string constant
    if (not is_numeric) and (not is_bytes) and (value != str(sideB_constant_value)):
        equivalent_constant = False
        
    if not equivalent_constant:
        logger.log_msg(f'{msg_package}/{msg_name} constant {name} has value {value} in {sideA} but value {sideB_constant_value} in {sideB}')
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

    msg_package = message_obj.__module__.split('.')[0]
    msg_name = message_obj.__name__

    # Automatically accept empty messages
    if proto_field.type == 'google.protobuf.Empty':
        if message_obj.__slots__ and message_obj.__slots__[0] != '_check_fields':
            logger.log_msg(f'Message type {msg_package}/{msg_name} is empty in {sideA} but not in {sideB}')
            return False
        return True

    slot_label = proto_field.name if sideB == 'Noetic' else f'_{proto_field.name}' # ROS2 slots have a leading underscore
    if slot_label not in message_obj.__slots__ and proto_field.type != 'google.protobuf.Empty':
        logger.log_msg(f'Message type {msg_package}/{msg_name} has field {proto_field.name} in {sideA} but not in {sideB}')
        if override:
            fields_to_delete.add(proto_field.name)
            return True
        else:
            return False

    sideA_msg_type: str = proto_field.type.replace('_msg_proto.', '.').replace('.', '/')

    if sideB == 'Noetic':
        corresponding_field_idx = message_obj.__slots__.index(proto_field.name)
        sideB_msg_type: str = message_obj._slot_types[corresponding_field_idx]
    else:
        sideB_msg_type: str = message_obj._fields_and_field_types[proto_field.name]

    # Check to see if it's a repeated message. There are a couple different syntaxes for this to acocunt for
    if sideB_msg_type.endswith(']'):
        sideB_msg_type = sideB_msg_type[:sideB_msg_type.find('[')]
        is_repeated = True
    elif sideB_msg_type.startswith('sequence<'):
        sideB_msg_type = sideB_msg_type[len('sequence<'):-1]
        if sideB_msg_type.find(',') >= 0:
            sideB_msg_type = sideB_msg_type[:sideB_msg_type.find(',')]
        is_repeated = True
    else:
        is_repeated = False

    if is_repeated and proto_field.cardinality != FieldCardinality.REPEATED and proto_field.type != 'bytes':
        logger.log_msg(f'{msg_package}/{proto_field.name} is an array in {sideB} but not in {sideA}')
        if override:
            fields_to_delete.add(proto_field.name)
            return True
        else:
            return False

    if not are_types_equivalent(sideB_msg_type, sideA_msg_type):
        logger.log_msg(f'Message type {msg_package}/{proto_field.name} has type {sideA_msg_type} in {sideA} but type {sideB_msg_type} in {sideB}')
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
    
    msg_package = message_obj.__module__.split('.')[0]
    msg_name = message_obj.__name__

    if fields_to_delete:
        logger.log_msg(f'{msg_package}/{msg_name} comptibility overriden by ignoring fields:')
        [logger.log_msg(f'\t{name}') for name in fields_to_delete]
        logger.log_msg('\n')

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
    try:
        imported_package = loaded_msg_packages.get(f'{msg_package}.{msg_class}', importlib.import_module(f'{msg_package}.{msg_class}'))
    except ModuleNotFoundError:
        logger.log_msg(f'Unable to import {msg_package}.{msg_class}')
        return False

    # Ensure that the message package contains the message type as well
    if not hasattr(imported_package, msg_name):
        logger.log_msg(f'Package {msg_package}/{msg_class} does not contain the interface type {msg_name}')
        return False
    ros_msg_class = getattr(imported_package, msg_name)

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
                ros_msg_obj = ros_msg_class._request_class if sideB == 'Noetic' else ros_msg_class.Request
            elif msg_class == 'srv' and message_element.name.endswith('Response'):
                ros_msg_obj = ros_msg_class._response_class if sideB == 'Noetic' else ros_msg_class.Response
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

            # Check for values that exist in sideB but not in sideA
            for elem in ros_msg_obj.__slots__:
                if elem == '_check_fields': continue
                if sideB != 'Noetic': elem = elem[1:]
                if elem not in matched_fields and elem not in fields_to_delete:
                    logger.log_msg(f'{msg_package}/{msg_name} has field {elem} in {sideB} but not in {sideA}')
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

def get_all_known_message_types_ros1() -> Dict[str, List[str]]:
    import rospkg
    import rosmsg
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

def get_all_known_message_types_ros2() -> Dict[str, List[str]]:
    import ros2interface.api

    # Create a lookup for all message types known in ROS2
    message_lookup = ros2interface.api.get_message_interfaces()
    for msg_types in message_lookup.values():
        msg_types[:] = [msg_type.removeprefix('msg/') for msg_type in msg_types]

    # Create a lookup for all service types known in ROS2
    service_lookup = ros2interface.api.get_service_interfaces()
    for srv_types in service_lookup.values():
        srv_types[:] = [srv_type.removeprefix('srv/') for srv_type in srv_types]

    return message_lookup, service_lookup

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proto-path", type=str, required=True)
    parser.add_argument("--sideA", type=str, required=True)
    parser.add_argument("--sideB", type=str, required=True)

    args = parser.parse_args()
    proto_path = args.proto_path

    # There are the ROS distros ('Noetic', 'Humble', 'Lyrical', etc.)
    global sideA, sideB
    sideA = args.sideA.capitalize()
    sideB = args.sideB.capitalize()

    if sideB == 'Noetic':
        message_lookup, service_lookup = get_all_known_message_types_ros1()
    else:
        message_lookup, service_lookup = get_all_known_message_types_ros2()
    msg_overrides = os.getenv('COMPAT_OVERRIDES', '').split(' ')

    missed_packages = set()
    deleted_files = set()

    logger = Logger(os.path.join(proto_path, 'log', f'{sideB}_bridge.txt'))
    logger.log_msg(f'{msg_overrides=}\n')
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
            logger.log_msg(f'Deleting {file_path}\n')
            deleted_files.add(filename)
            os.remove(file_path)
            continue

        if not check_interface_compatibility(msg_package, msg_class, msg_typename, str(file_path), msg_overrides, logger):
            logger.log_msg(f'Message {msg_package}/{msg_typename} is not compatible between {sideA} and {sideB}')
            logger.log_msg(f'Deleting {file_path}\n')
            deleted_files.add(filename)
            os.remove(file_path)
            continue

    if len(missed_packages) > 0:
        logger.log_msg('Unable to find matching interfaces for:')
        for missed_package in sorted(missed_packages):
            logger.log_msg(f'\t{missed_package}')

    # Do one more sweep of the files to remove files or imports related to files that we have deleted
    files_deleted = 1
    while files_deleted > 0:
        files_to_delete = []
        for file_path in Path(proto_path).rglob('*.proto'):
            with open(file_path, 'r') as f:
                lines = f.readlines()
            header, messages, services = split_proto_text(lines)

            with open(file_path, 'w') as f:
                line: str
                invalidated_references = []
                for line in header:
                    # We're only filtering imports
                    if not line.startswith('import'): 
                        f.write(line)
                        continue

                    import_filename = line[len('import "'):-3]
                    if import_filename in deleted_files:
                        # File names have structure msg_package.msg.MsgName.proto
                        msg_name = file_path.name[:-6].replace('.', '/') # can't use removesuffix for ROS1 compatibility
                        deleted_msg_name = import_filename[:-6].replace('.', '/')
                        logger.log_msg(f'{msg_name} relies on a deleted file {import_filename}')
                        if msg_name in msg_overrides:
                            logger.log_msg(f'Overriding by removing reference to {import_filename}\n')
                            invalidated_references.append(deleted_msg_name)
                            continue
                        else:
                            logger.log_msg(f'Deleting {file_path}\n')
                            files_to_delete.append(file_path)
                            break
                    f.write(line)

                for message in messages:
                    for line in message:
                        if line.startswith('\t') and line.count('.') and not line.count('google.protobuf.'):
                            # Message lines have structure \t [repeated] msg_package_msg_proto.MsgName field = x;
                            msg_package_part, msg_name_part = line.strip().split('.')
                            if msg_package_part.startswith('repeated '):
                                msg_package_part = msg_package_part[len('repeated'):]
                            msg_package = msg_package_part[:-10] # remove _msg_proto
                            msg_name = msg_name_part.split(' ')[0]
                            if f'{msg_package}/msg/{msg_name}' in invalidated_references:
                                continue
                        f.write(line)

                f.writelines(services)

        files_deleted = 0
        for file_path in files_to_delete:
            deleted_files.add(os.path.basename(file_path))
            os.remove(file_path)
            files_deleted += 1

if __name__ == "__main__":
    main()