import os
import sys
import ros2interface.api

generated_files = []
message_dependencies = set[str]()

types_map = {
    'builtin_interfaces/Time': 'google.protobuf.Timestamp',
    'builtin_interfaces/Duration': 'google.protobuf.Duration',
    # protobuf does not support integer types less that 32 bits
    'uint8': 'uint32', 
    'uint16': 'uint32',
    'int8': 'int32',
    'int16': 'int32',
    'boolean': 'bool',
    'octet': 'uint32',
}

bytes_types = ('int8', 'uint8', 'octet')

imports_map = {
    'builtin_interfaces/Time': 'google/protobuf/timestamp.proto',
    'builtin_interfaces/Duration': 'google/protobuf/duration.proto',
}

class Logger:
    def __init__(self, path: str):
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.file = open(path, 'w')

    def log_msg(self, msg: str):
        self.file.write(f'{msg}\n')
        print(msg)

def resolve_type(field_type: str) -> str:
    """
    Convert a ros2interface API field type to a valid proto type
    Eg:
     - int16                       => int32
     - int8[]                      => bytes
     - geometry_msgs/Twist[]       => repeated geometry_msgs_proto.Twist
     - sequence<std_msgs/String,5> => repeated std_msgs_proto.String
     - builtin_interfaces/Duration => google.protobuf.Duration
    """

    ### Builtin types:
    if field_type in types_map:
        return types_map[field_type]
    
    ### Byte strings
    # If it contains a byte type but wasn't caught by the builtin map, it's a byte string
    elif any([byte_type in field_type for byte_type in bytes_types]):
        return 'bytes'

    ### Repeated types (either builtin or ROS type)
    # Dynamic sized array
    if field_type.startswith('sequence<'):
        if ',' in field_type:
            field_type = field_type[:field_type.find(',')] + '>'
        return 'repeated ' + resolve_type(field_type.removeprefix('sequence<')[:-1])
    # Constant sized array
    elif field_type.endswith(']'):
        return 'repeated ' + resolve_type(field_type[:field_type.find('[')])
    # Constant sized array
    elif field_type.endswith('>'):
        # We don't enforce string sizes
        if field_type.startswith('string'):
            return 'string'
        else:
            return 'repeated ' + resolve_type(field_type[:field_type.find('<')])
        
    ### ROS types
    else:
        if '/' in field_type:
            package_name = field_type[:field_type.find('/')]
            field_type = field_type.replace(package_name, f'{package_name}_msg_proto')
        return field_type.replace('/', '.')
    
def resolve_import(field_type: str) -> str:
    """
    Converts ROS2 field types to proto types.
    Eg:
     - std_msgs/String[]             => std_msgs.msg.String.proto
     - geometry_msgs/Vector3         => geometry_msgs.msg.Vector3.proto
     - sequence<sensor_msgs/Image,4> => sensor_msgs.msg.Image.proto
     - builtin_interfaces/Time       => google/protobuf/timestamp.proto
    """

    if field_type.endswith(']'):
        field_type = field_type[:field_type.find('[')]

    if field_type.startswith('sequence<'):
        if ',' in field_type:
            field_type = field_type[:field_type.find(',')] + '>'
        field_type = field_type.removeprefix('sequence<')[:-1]

    if field_type in imports_map:
        return imports_map[field_type]

    return field_type.replace('/', '.msg.') + '.proto'

def resolve_all_imports(msg_interfaces: list) -> str:
    """
    Loops through provided interfaces and adds import lines for all dependencies
    
    Example Output:
        import "geometry_msgs.Vector3.proto";
        import "geometry_msgs.Point.proto";
        import "google/protobuf/timestamp.proto";
    """

    string = ""
    
    imported_names = set()
    for msg_interface in msg_interfaces:
        for field_name, field_type in msg_interface._fields_and_field_types.items():
            if '/' in field_type:
                imported_type_name = resolve_import(field_type)
                if imported_type_name not in imported_names:
                    imported_names.add(imported_type_name)
                    string += f'import "{imported_type_name}";\n'
                if field_type not in types_map.keys():
                    message_dependencies.add(resolve_import(field_type))

    return string

def get_message_proto_string(msg_interface):
    string = ""

    # Resolve the actual message definition
    string += f'message {msg_interface.__name__.replace("_", "")} {"{"}\n'

    # Resolve any constants in the message as an enum
    constants = msg_interface.__class__.__prepare__('', '')
    constants = {key: val for (key, val) in constants.items() if not key.endswith('__DEFAULT')}
    if len(constants):
        string += '\t// Constants \n'
        for idx, (enum_name, enum_val) in enumerate(constants.items()):
            string += (f'\t// {enum_name} = {enum_val};\n')
        string += '\n'

    idx = 1
    for field_name, field_type in msg_interface._fields_and_field_types.items():
        string += f'\t{resolve_type(field_type)} {field_name} = {idx};\n'
        idx += 1

    # Empty interface, we need to add an empty message here
    if not msg_interface._fields_and_field_types:
        string += '\tgoogle.protobuf.Empty __ros_bridge_grpc_empty_msg = 1;\n'

    string += '}\n'

    return string

def ros2_message_to_proto_msg(msg_package: str, msg_type: str, proto_path: str, logger: Logger) -> None:
    full_message_type = ros2interface.api.utilities.get_message(msg_package + '/' + msg_type)

    if 'wstring' in full_message_type._fields_and_field_types.values():
        logger.log_msg(f'Cannot bridge {msg_package}/{msg_type} as wstring is not supported in ROS1')
        return

    file_name = f'{msg_package}.msg.{msg_type}.proto'
    file_path = os.path.join(proto_path, file_name)

    if file_name in generated_files:
        return

    generated_files.append(file_name)
    with open(file_path, 'w') as f:
        f.write('syntax = "proto3";\n')
        f.write(f'package {msg_package}_msg_proto;\n')
        f.write(f'import "google/protobuf/empty.proto";\n')

        f.write(resolve_all_imports([full_message_type]))
        f.write(get_message_proto_string(full_message_type))

        # Add in the gRPC interface
        f.write(
            f'message {msg_type}Packet {"{"}\n'
            f'    string topic = 1;\n'
            f'    {msg_type} message = 2;\n'
            '}\n'
            f'service Send{msg_type}MsgROS {"{"}\n'
            f'    rpc SendROSMessage ({msg_type}Packet) returns (google.protobuf.Empty) {"{}"}\n'
            '}\n'
        )

def ros2_service_to_proto_srv(msg_package: str, srv_type: str, proto_path: str, logger: Logger) -> None:
    full_service_type = ros2interface.api.utilities.get_service(msg_package + '/' + srv_type)

    if 'wstring' in full_service_type.Request._fields_and_field_types.values() or \
       'wstring' in full_service_type.Response._fields_and_field_types.values():
        logger.log_msg(f'Cannot bridge {msg_package}/srv/{srv_type} as wstring is not supported in ROS1')
        return
    
    file_name = f'{msg_package}.srv.{srv_type}.proto'
    file_path = os.path.join(proto_path, file_name)

    if file_name in generated_files:
        return
    
    generated_files.append(file_name)
    with open(file_path, 'w') as f:
        f.write('syntax = "proto3";\n')
        f.write(f'package {msg_package}_srv_proto;\n')
        f.write(f'import "google/protobuf/empty.proto";\n')

        f.write(resolve_all_imports([full_service_type.Request, full_service_type.Response]))
        f.write(get_message_proto_string(full_service_type.Request))
        f.write(get_message_proto_string(full_service_type.Response))

        # Add in the gRPC interface
        f.write(
            f'message {srv_type}RequestPacket {"{"}\n'
            f'    string service = 1;\n'
            f'    {srv_type}Request request = 2;\n'
            '}\n'
            f'message {srv_type}ResponsePacket {"{"}\n'
            f'    string service = 1;\n'
            f'    {srv_type}Response response = 2;\n'
            '}\n'
            f'service Send{srv_type}SrvROS {"{"}\n'
            f'    rpc CallROSService ({srv_type}RequestPacket) returns ({srv_type}ResponsePacket) {"{}"}\n'
            '}\n'
        )

def main(code_gen_path: str, allowed_types: list[str]):
    global message_dependencies
    logger = Logger(os.path.join(code_gen_path, 'log', 'ros2_bridge.txt'))

    if not code_gen_path.startswith('/') and not code_gen_path.startswith('.'):
        code_gen_path = os.path.join('.', code_gen_path)
    proto_path = os.path.join(code_gen_path, 'proto')
    cpp_path = os.path.join(code_gen_path, 'proto_cpp')
    grpc_path = os.path.join(code_gen_path, 'grpc_cpp')

    for path in [proto_path, cpp_path, grpc_path]:
        if not os.path.exists(path):
            os.mkdir(path)

    logger.log_msg(f'Path: {os.getenv("ROS_PACKAGE_PATH", "None")}')
    logger.log_msg(f'Allowed types: {allowed_types}')

    built_packages = set()
    logger.log_msg('\nMESSAGES:')
    for msg_package, msg_types in ros2interface.api.get_message_interfaces().items():
        all_allowed: bool = f'{msg_package}/msg/ALL' in allowed_types
        logger.log_msg(f'{msg_package}:')
        for msg_type in msg_types:
            if not all_allowed and f'{msg_package}/{msg_type}' not in allowed_types:
                logger.log_msg(f'\t{msg_type}')            
                continue 
            logger.log_msg(f'\t{msg_type} [BUILT]')            
            trimmed_msg_type = msg_type[4:]
            ros2_message_to_proto_msg(msg_package, trimmed_msg_type, proto_path, logger)
            built_packages.add(msg_package)

        if msg_package not in built_packages:
            continue

        logger.log_msg(f'Message dependencies for built messages in {msg_package}: {message_dependencies}')
        while len(message_dependencies) > 0:
            tmp_message_dependencies = list(message_dependencies)
            message_dependencies = set[str]()
            for msg_type in tmp_message_dependencies:
                msg_package, _, trimmed_msg_type, _ = msg_type.split('.')
                ros2_message_to_proto_msg(msg_package, trimmed_msg_type, proto_path, logger)

    logger.log_msg('\nSERVICES:')
    for msg_package, srv_types in ros2interface.api.get_service_interfaces().items():
        all_allowed: bool = f'{msg_package}/srv/ALL' in allowed_types
        logger.log_msg(f'{msg_package}:')
        for srv_type in srv_types:
            if not all_allowed and f'{msg_package}/{srv_type}' not in allowed_types:
                logger.log_msg(f'\t{srv_type}')            
                continue 
            logger.log_msg(f'\t{srv_type} [BUILT]')            
            trimmed_srv_type = srv_type[4:]
            ros2_service_to_proto_srv(msg_package, trimmed_srv_type, proto_path, logger)
            built_packages.add(msg_package)

        if msg_package not in built_packages:
            continue

        logger.log_msg(f'Message dependencies for built messages in {msg_package}: {message_dependencies}')
        while len(message_dependencies) > 0:
            tmp_message_dependencies = list(message_dependencies)
            message_dependencies = set[str]()
            for msg_type in tmp_message_dependencies:
                logger.log_msg(f'{msg_type}')            
                msg_package, _, trimmed_msg_type, _ = msg_type.split('.')
                ros2_message_to_proto_msg(msg_package, trimmed_msg_type, proto_path, logger)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('Missing required argument code_gen_path')
        exit(1)

    code_gen_path = sys.argv[1]
    main(code_gen_path, allowed_types=sys.argv[2:])