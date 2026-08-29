#!/usr/bin/env python3

import os
import sys
import yaml
import subprocess
from collections import defaultdict

def main(config_file: str):
    with open(config_file, 'r') as file:
        config_dict = yaml.safe_load(file)

    output_dict = defaultdict(str)

    # Distro selection
    output_dict['ROS_BRIDGE_GRPC_SIDE_A_DISTRO'] = config_dict.get('side_A_distro', 'humble')
    output_dict['ROS_BRIDGE_GRPC_SIDE_B_DISTRO'] = config_dict.get('side_B_distro', 'noetic')

    match output_dict['ROS_BRIDGE_GRPC_SIDE_A_DISTRO']:
        case ('noetic'):
            raise RuntimeError(f'SideA must be a ROS2 distro. You gave {output_dict["ROS_BRIDGE_GRPC_SIDE_A_DISTRO"]}')
        case ('humble'|'iron'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_A_UBUNTU'] = 'jammy'
        case ('jazzy'|'kilted'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_A_UBUNTU'] = 'noble'
        case ('lyrical'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_A_UBUNTU'] = 'resolute'

    match output_dict['ROS_BRIDGE_GRPC_SIDE_B_DISTRO']:
        case ('noetic'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_B_UBUNTU'] = 'focal'
        case ('humble'|'iron'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_B_UBUNTU'] = 'jammy'
        case ('jazzy'|'kilted'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_B_UBUNTU'] = 'noble'
        case ('lyrical'):
            output_dict['ROS_BRIDGE_GRPC_SIDE_B_UBUNTU'] = 'resolute'

    # Custom message types
    git_urls = {'side_A': '', 'side_B': ''}
    custom_packages = []
    output_dict['ROS_BRIDGE_GRPC_CUSTOM_PACKAGES'] = ""
    for custom_package in config_dict.get('custom_packages', list[dict[str, str]]()):
        for version in ['side_A', 'side_B']:
            if git_url := custom_package.get(f'{version}_url', None):
                git_urls[version] += f'{git_url};'

            elif local_path := custom_package.get(f'{version}_path', None):
                source_dir, _ = os.path.split(os.path.abspath(__file__))
                mapped_dir = os.path.join(source_dir, '..', 'docker', 'mapped', version)

                _, target_dir_name = os.path.split(local_path)
                mapped_target = os.path.join(mapped_dir, target_dir_name)
                os.makedirs(mapped_target, exist_ok=True)
                subprocess.run(['sudo', 'mount', '--bind', local_path, mapped_target])

            else:
                continue

        custom_packages.append(custom_package["package_name"])
        output_dict['ROS_BRIDGE_GRPC_CUSTOM_PACKAGES'] += f' {custom_package["package_name"]}'
        output_dict['ROS_BRIDGE_GRPC_MESSAGE_PACKAGES'] += f' {custom_package["package_name"]}'

    output_dict['ROS_BRIDGE_GRPC_USER_SIDE_A_REPOS'] = git_urls['side_A']
    output_dict['ROS_BRIDGE_GRPC_USER_SIDE_B_REPOS'] = git_urls['side_B']

    # Message types
    system_packages = " "
    allowed_types = " "
    for package_id, message_types in config_dict.get('msg_packages', dict()).items():
        msg_package, package_type = package_id.split('/')
        if msg_package not in custom_packages:
            system_packages += f'{msg_package} '
        for msg_type in message_types:
            allowed_types += f'{msg_package}/{package_type}/{msg_type} '
    output_dict['ROS_BRIDGE_GRPC_MESSAGE_PACKAGES'] += system_packages
    output_dict['ROS_BRIDGE_GRPC_SYSTEM_PACKAGES'] += system_packages.replace('_', '-')
    output_dict['ROS_BRIDGE_GRPC_ALLOWED_TYPES'] += allowed_types

    # Compatibiltiy overrides
    output_dict['ROS_BRIDGE_GRPC_COMPAT_OVERRIDES'] = ' '.join(config_dict.get('compatibility_overrides', list[str]()))

    # Print the commands to be executed in the shell
    for key, value in output_dict.items():
        print(f'export {key}="{value}"')

if __name__ == '__main__':
    if len(sys.argv) == 1:
        raise RuntimeError('No configuration file provided!')

    filename = sys.argv[1]
    main(filename)