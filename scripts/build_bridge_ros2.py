import os
import sys
import subprocess
import ros2interface.api
from visualization_msgs.msg import Marker
from moveit_msgs.msg import Constraints

generated_files = []

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
    # TODO: explore the use of 'bytes' here
    'wstring': 'string',
}

imports_map = {
    'builtin_interfaces/Time': 'google/protobuf/timestamp.proto',
    'builtin_interfaces/Duration': 'google/protobuf/duration.proto',
}

def resolve_type(field_type: str) -> str:
    if field_type in types_map:
        return types_map[field_type]

    # Dynmaic sized array
    if field_type.startswith('sequence<'):
        if ',' in field_type:
            field_type = field_type[:field_type.find(',')] + '>'
        return 'repeated ' + resolve_type(field_type.removeprefix('sequence<')[:-1])
    # Constant sized array
    elif field_type.endswith(']'):
        return 'repeated ' + resolve_type(field_type[:field_type.find('[')])
    # Constant sized array
    elif field_type.endswith('>'):
        return 'repeated ' + resolve_type(field_type[:field_type.find('<')])
    # Single item
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

def ros2_message_to_proto_msg(msg_package: str, msg_type: str, proto_path: str) -> None:
    full_message_type = ros2interface.api.utilities.get_message(msg_package + '/' + msg_type)

    file_name = f'{msg_package}.{msg_type}.proto'
    file_path = os.path.join(proto_path, file_name)
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
            f'service Send{msg_type}ROS2 {"{"}\n'
            f'    rpc SendROSMessage ({msg_type}Packet) returns (google.protobuf.Empty) {"{}"}\n'
            f'{"}"}\n'
        )

def main(proto_path: str):
    all_msgs = ros2interface.api.get_message_interfaces()
    for msg_package, msg_types in all_msgs.items():
        for msg_type in msg_types:
            if not msg_type.startswith('msg/'):
                print(f'Skipping unknown interface {msg_package}/{msg_type}')
                continue
            ros2_message_to_proto_msg(msg_package, msg_type[4:], proto_path)

    # Invoke protoc on the generated files
    if not proto_path.startswith('/') and not proto_path.startswith('.'):
        proto_path = os.path.join('.', proto_path)
    cpp_path = os.path.join(proto_path, 'cpp')
    grpc_path = os.path.join(proto_path, 'grpc')
    if not os.path.exists(cpp_path):
        os.mkdir(cpp_path)
    subprocess.run(['protoc', f'--proto_path={proto_path}', f'--cpp_out={cpp_path}', f'--grpc_out={grpc_path}', '--plugin=protoc-gen-grpc=/home/alex/.local/src/grpc/install/bin/grpc_cpp_plugin', *generated_files])

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('Missing required argument proto_path')
        exit(1)

    proto_path = sys.argv[1]
    main(proto_path)