import os
import sys
import subprocess
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
            field_type = field_type.replace(package_name, f'{package_name}_proto')
        return field_type.replace('/', '.')
    
def resolve_import(field_type: str) -> str:   
    if field_type.endswith(']'):
        field_type = field_type[:field_type.find('[')]

    if field_type.startswith('sequence<'):
        if ',' in field_type:
            field_type = field_type[:field_type.find(',')] + '>'
        field_type = field_type.removeprefix('sequence<')[:-1]

    if field_type in imports_map:
        return imports_map[field_type]

    return field_type.replace('/', '.') + '.proto'

def resolve_datatype(field_type: str) -> str:
    import_name = resolve_import(field_type)
    # Remove the .proto extension
    import_name = import_name[:-6]
    return import_name.replace('.', '/')

def ros2_message_to_proto_msg(msg_package: str, msg_type: str, proto_path: str, logger: Logger) -> None:
    full_message_type = ros2interface.api.utilities.get_message(msg_package + '/' + msg_type)

    if 'wstring' in full_message_type._fields_and_field_types.values():
        logger.log_msg(f'Cannot bridge {msg_package}/{msg_type} as wstring is not supported in ROS1')
        return

    file_name = f'{msg_package}.{msg_type}.proto'
    file_path = os.path.join(proto_path, file_name)

    if file_name in generated_files:
        return

    generated_files.append(file_name)
    with open(file_path, 'w') as f:
        f.write('syntax = "proto3";\n')
        f.write(f'package {msg_package}_proto;\n')
        f.write(f'import "google/protobuf/empty.proto";\n')

        # Resolve the imports
        field_name: str
        imported_names = set()
        for field_name, field_type in full_message_type._fields_and_field_types.items():
            if '/' in field_type:
                imported_type_name = resolve_import(field_type)
                if imported_type_name not in imported_names:
                    imported_names.add(imported_type_name)
                    f.write(f'import "{imported_type_name}";\n')
                if field_type not in types_map.keys():
                    message_dependencies.add(resolve_datatype(field_type))

        # Resolve the actual message definition
        f.write(f'message {msg_type} {"{"}\n')

        # Resolve any constants in the message as an enum
        constants = full_message_type.__class__.__prepare__('', '')
        constants = {key: val for (key, val) in constants.items() if not key.endswith('__DEFAULT')}
        if len(constants):
            f.write('\t// Constants \n')
            for idx, (enum_name, enum_val) in enumerate(constants.items()):
                f.write(f'\t// {enum_name} = {enum_val};\n')
            f.write('\n')

        idx = 1
        for field_name, field_type in full_message_type._fields_and_field_types.items():
            f.write(f'\t{resolve_type(field_type)} {field_name} = {idx};\n')
            idx += 1
        f.write('}\n')

        # Add in the gRPC interface
        f.write(
            f'message {msg_type}Packet {"{"}\n'
            f'    string topic = 1;\n'
            f'    {msg_type} message = 2;\n'
             '}\n'
        )

        f.write(
            f'service Send{msg_type}ROS {"{"}\n'
            f'    rpc SendROSMessage ({msg_type}Packet) returns (google.protobuf.Empty) {"{}"}\n'
            f'{"}"}\n'
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

    built_packages = set()
    all_msgs = ros2interface.api.get_message_interfaces()
    logger.log_msg('Detected message types:')
    for msg_package, msg_types in all_msgs.items():
        all_allowed: bool = f'{msg_package}/ALL' in allowed_types
        logger.log_msg(f'{msg_package}:')
        for msg_type in msg_types:
            logger.log_msg(f'\t{msg_type}')
            if not msg_type.startswith('msg/'):
                logger.log_msg(f'Skipping unknown interface {msg_package}/{msg_type}')
                continue
            
            trimmed_msg_type = msg_type[4:]
            if not all_allowed and f'{msg_package}/{trimmed_msg_type}' not in allowed_types:
                continue 
            ros2_message_to_proto_msg(msg_package, trimmed_msg_type, proto_path, logger)
            built_packages.add(msg_package)

        if msg_package not in built_packages:
            continue

        logger.log_msg(f'Message dependencies for built messages in {msg_package}: {message_dependencies}')
        while len(message_dependencies) > 0:
            tmp_message_dependencies = list(message_dependencies)
            message_dependencies = set[str]()
            for msg_type in tmp_message_dependencies:
                msg_package, trimmed_msg_type = msg_type.split('/')
                ros2_message_to_proto_msg(msg_package, trimmed_msg_type, proto_path, logger)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('Missing required argument code_gen_path')
        exit(1)

    code_gen_path = sys.argv[1]
    main(code_gen_path, allowed_types=sys.argv[2:])