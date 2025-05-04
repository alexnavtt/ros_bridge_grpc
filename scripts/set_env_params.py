#!/usr/bin/env python3

import os
import sys
import yaml
import subprocess

def main(config_file: str):
    with open(config_file, 'r') as file:
        config_dict = yaml.safe_load(file)

    output_dict = dict()

    # ROS1 config
    if ros1_config := config_dict.get('ros1', None):
        output_dict['ROS_BRIDGE_GRPC_ROS1_DISTRO'] = ros1_config.get('distro', 'noetic')
        output_dict['ROS_BRIDGE_GRPC_ROS1_URI'] = ros1_config.get('ROS_MASTER_URI', 'http://localhost:11311')
        if ros_hostname := ros1_config.get('ROS_HOSTNAME', None):
            output_dict['ROS_BRIDGE_GRPC_ROS1_HOSTNAME'] = ros_hostname
        if ros_ip := ros1_config.get('ROS_IP', None):
            output_dict['ROS_BRIDGE_GRPC_ROS1_IP'] = ros_ip

    # ROS2 config
    if ros2_config := config_dict.get('ros2', None):
        output_dict['ROS_BRIDGE_GRPC_ROS2_DISTRO'] = ros2_config.get('distro', 'humble')
        if ros_domain_id := ros2_config.get('ROS_DOMAIN_ID', None):
            output_dict['ROS_BRIDGE_GRPC_ROS_DOMAIN_ID'] = ros_domain_id
        if rmw_implementation := ros2_config.get('RMW_IMPLEMENTATION', 'cyclonedds_cpp'):
            output_dict['ROS_BRIDGE_GRPC_RMW_IMPLEMENTATION'] = rmw_implementation
        if cyclonedds_uri := ros2_config.get('CYCLONEDDS_URI', None):
            output_dict['ROS_BRIDGE_GRPC_CYCLONEDDS_URI'] = cyclonedds_uri
        
    # Message types
    system_packages = ""
    allowed_types = ""
    for msg_package, message_types in config_dict.get('msg_packages', dict()).items():
        system_packages += f'{msg_package} '
        for msg_type in message_types:
            allowed_types += f'{msg_package}/{msg_type} '
    output_dict['ROS_BRIDGE_GRPC_MESSAGE_PACKAGES'] = system_packages
    output_dict['ROS_BRIDGE_GRPC_SYSTEM_PACKAGES'] = system_packages.replace('_', '-')
    output_dict['ROS_BRIDGE_GRPC_ALLOWED_TYPES'] = allowed_types

    # Custom message types
    git_urls = ""
    for custom_package in config_dict.get('custom_packages', list[dict[str, str]]()):

        if git_url := custom_package.get('url', None):
            git_urls += f'{git_url};'

        elif local_path := custom_package.get('path', None):
            source_dir, _ = os.path.split(os.path.abspath(__file__))
            mapped_dir = os.path.join(source_dir, '..', 'docker', 'mapped')

            _, target_dir_name = os.path.split(local_path)
            mapped_target = os.path.join(mapped_dir, target_dir_name)
            os.makedirs(mapped_target, exist_ok=True)
            subprocess.run(['sudo', 'mount', '--bind', local_path, mapped_target])

        else:
            continue

        output_dict['ROS_BRIDGE_GRPC_MESSAGE_PACKAGES'] += f' {custom_package["package_name"]}'

    output_dict['ROS_BRIDGE_GRPC_USER_REPOS'] = git_urls

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