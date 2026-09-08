# Default args just to make Dockerfile linters happy
ARG SIDE_A_DISTRO=humble
ARG SIDE_B_DISTRO=noetic
ARG SIDE_A_UBUNTU=jammy
ARG SIDE_B_UBUNTU=focal
ARG BRIDGE_TYPE="regular"

# -------------------------------------------------------------------------------------------------
# Base Images
# -------------------------------------------------------------------------------------------------

FROM grpc_bridge_base:${SIDE_A_UBUNTU} AS side_a_grpc_base
FROM grpc_bridge_base:${SIDE_B_UBUNTU} AS side_b_grpc_base

# -------------------------------------------------------------------------------------------------
# Side A Generate Proto Definitions
# -------------------------------------------------------------------------------------------------

FROM ros:${SIDE_A_DISTRO}-ros-base AS side_a_ros_base
# Note: SideA is always a ROS2 distro

ARG SIDE_A_DISTRO

SHELL ["/bin/bash", "-lc"]
ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install cyclonedds
RUN apt update \
    && apt install -y ros-${SIDE_A_DISTRO}-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# Install system message types
ARG SYSTEM_PACKAGES=""
RUN apt update && \
    apt install -y python3-pip openssh-client && \
    if [ ! -z "${SYSTEM_PACKAGES}" ]; then \
        for pkg in ${SYSTEM_PACKAGES}; do\
            apt install -y ros-${SIDE_A_DISTRO}-$pkg; \
        done; \
    fi && \
    rm -rf /var/lib/apt/lists/*

    
# Copy user packages into the image
COPY docker/mapped/side_A /user_ws/src/
    
# Clone git-based user packages
ARG USER_SIDE_A_REPOS=""
ARG GIT_RECLONE=1
WORKDIR /user_ws/src
RUN --mount=type=ssh \
    mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    if [ ! -z "${USER_SIDE_A_REPOS}" ]; then\
        echo "${USER_SIDE_A_REPOS}" | tr ";" "\n" | while read -r repo; do \
            if [ -n "$repo" ]; then \
                echo "Cloning $repo"; \
                eval "git clone $repo"; \
            fi; \
        done;\
    fi

# Build user packages
ARG CUSTOM_PACKAGES=""
WORKDIR /user_ws
RUN rosdep update --include-eol-distros \
    && apt update \
    && source /opt/ros/${SIDE_A_DISTRO}/setup.bash && \
    for pkg in ${CUSTOM_PACKAGES}; do \
        pkg_path=$(colcon list | awk -v pkg_name="$pkg" '$1 == pkg_name {print $2}'); \
        rosdep install --from-paths "$pkg_path" -i -y; \
    done \
    && rm -rf /var/lib/apt/lists*
RUN source /opt/ros/${SIDE_A_DISTRO}/setup.bash && colcon build --packages-up-to ${CUSTOM_PACKAGES} && echo "source /user_ws/install/setup.bash" >> ~/.profile

# Copy the generated protoc and gRPC libraries
COPY --from=side_a_grpc_base /install /install
ENV PATH="/install/bin:$PATH"

# Generate proto files
ARG ALLOWED_TYPES=""
COPY scripts/build_bridge_ros2.py /scripts/build_bridge_ros2.py
RUN source /opt/ros/${SIDE_A_DISTRO}/setup.bash \
    && source /user_ws/install/setup.bash \
    && mkdir /generated \
    && python3 /scripts/build_bridge_ros2.py /generated ${ALLOWED_TYPES}

# -------------------------------------------------------------------------------------------------
# Side B Evaluate Proto Definitions
# -------------------------------------------------------------------------------------------------

FROM ros:${SIDE_B_DISTRO}-ros-base AS side_b_ros_base
ARG SIDE_A_DISTRO
ARG SIDE_B_DISTRO

SHELL ["/bin/bash", "-lc"]
ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Fix ROS1 apt key issues
RUN if [ "${SIDE_B_DISTRO}" == "noetic" ]; then \
        mkdir -p /etc/apt/keyrings \
        && sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list' \
        && curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -; \
    fi

# Install system message types
ARG SYSTEM_PACKAGES=""
RUN apt update \
    && if [ "${SIDE_B_DISTRO}" == "noetic" ]; then \ 
        apt install -y python3-catkin-tools; \
    else \ 
        apt install -y ros-${SIDE_B_DISTRO}-rmw-cyclonedds-cpp; \
    fi \
    && apt install -y git python3-pip openssh-client \
    && if [ ! -z "${SYSTEM_PACKAGES}" ]; then \
        for pkg in ${SYSTEM_PACKAGES}; do\
            apt install -y ros-${SIDE_B_DISTRO}-$pkg; \
        done; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# Create a catkin/colcon workspace
WORKDIR /user_ws
RUN mkdir -p src \
    && source /opt/ros/${SIDE_B_DISTRO}/setup.bash \
    && (catkin build || colcon build)

# Copy user packages into the image
COPY docker/mapped/side_B /user_ws/src/
    
# Clone git-based user packages
ARG USER_SIDE_B_REPOS=""
ARG GIT_RECLONE=1
WORKDIR /user_ws/src
RUN --mount=type=ssh \
    mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    if [ ! -z "${USER_SIDE_B_REPOS}" ]; then\
        echo "${USER_SIDE_B_REPOS}" | tr ";" "\n" | while read -r repo; do \
            if [ -n "$repo" ]; then \
                echo "Cloning $repo"; \
                eval "git clone $repo"; \
            fi; \
        done;\
    fi

# Build user packages
ARG CUSTOM_PACKAGES=""
WORKDIR /user_ws
RUN rosdep update --include-eol-distros \
    && apt update \
    && source /opt/ros/${SIDE_B_DISTRO}/setup.bash && \
    for pkg in ${CUSTOM_PACKAGES}; do \
        pkg_path=$(catkin locate "$pkg") || pkg_path=$(colcon list | awk -v pkg_name="$pkg" '$1 == pkg_name {print $2}'); \
        rosdep install --from-paths "$pkg_path" -i -y; \
    done \
    && rm -rf /var/lib/apt/lists*

RUN source /opt/ros/${SIDE_B_DISTRO}/setup.bash \
    && (catkin build ${CUSTOM_PACKAGES} || colcon build --packages-up-to ${CUSTOM_PACKAGES}) \ 
    && echo "source /user_ws/devel/setup.bash || source /user_ws/install/setup.bash || true" >> ~/.profile

# Copy the generated protoc and gRPC libraries
COPY --from=side_b_grpc_base /install /install
ENV PATH="/install/bin:$PATH"

# Install dependencies for the script
RUN pip install proto-schema-parser

# Copy generated library code
COPY --from=side_a_ros_base /generated /generated

# Verify generated proto files
ARG ALLOWED_TYPES=""
ARG COMPAT_OVERRIDES=""
COPY scripts/evaluate_bridge.py /scripts/evaluate_bridge.py
RUN source /opt/ros/${SIDE_B_DISTRO}/setup.bash \
    && source ~/.profile \
    && COMPAT_OVERRIDES=${COMPAT_OVERRIDES} python3 /scripts/evaluate_bridge.py --proto-path /generated --sideA ${SIDE_A_DISTRO} --sideB ${SIDE_B_DISTRO}

# -------------------------------------------------------------------------------------------------
# ROS2 Generate Stage 2
# -------------------------------------------------------------------------------------------------

FROM side_a_ros_base AS side_a_generated_mirrored
FROM side_a_ros_base AS side_a_generated_regular

# Copy the updated generated library code after filtering
RUN rm -rf /generated
COPY --from=side_b_ros_base /generated /generated

FROM side_a_generated_${BRIDGE_TYPE} AS side_a_generated
ARG SIDE_A_DISTRO
ARG SIDE_B_DISTRO

# Run protoc to generate the base level proto_cpp and gRPC code
RUN mkdir -p /generated/proto_cpp \
    && mkdir -p /generated/grpc_cpp \
    && find /generated/proto -name '*.proto' |  \
    xargs /install/bin/protoc \
    --proto_path=/generated/proto \
    --cpp_out=/generated/proto_cpp \
    --grpc_out=/generated/grpc_cpp \
    --plugin=protoc-gen-grpc=/install/bin/grpc_cpp_plugin

# Generate C++ source code to translate between proto and ROS
RUN pip install proto-schema-parser
COPY scripts/generate_cpp_conversion_code.py /scripts/generate_cpp_conversion_code.py
RUN SIDE_A_DISTRO=${SIDE_A_DISTRO} SIDE_B_DISTRO=${SIDE_B_DISTRO} python3 /scripts/generate_cpp_conversion_code.py /generated

# -------------------------------------------------------------------------------------------------
# ROS2 Build
# -------------------------------------------------------------------------------------------------

FROM side_a_generated AS side_a_build

# Add the ROS2 package and compile
WORKDIR /colcon_ws
COPY ros2/ros2_bridge_grpc /colcon_ws/src/ros2/ros2_bridge_grpc
COPY common /common

ARG MESSAGE_PACKAGES
ENV MESSAGE_PACKAGES=${MESSAGE_PACKAGES}
RUN source /opt/ros/${SIDE_A_DISTRO}/setup.bash \
    && source ~/.profile \
    && CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && echo "source /colcon_ws/install/setup.bash" >> ~/.profile

COPY docker/entrypoints/run_ros2_bridge.bash /entrypoints/run_ros2_bridge.bash
COPY docker/entrypoints/run_ros2_bridge.bash /entrypoints/run_ros_bridge.bash
RUN chmod +x /entrypoints/run_ros2_bridge.bash && chmod +x /entrypoints/run_ros_bridge.bash

# -------------------------------------------------------------------------------------------------
# ROS1 Build
# -------------------------------------------------------------------------------------------------

FROM side_b_ros_base AS side_b_build

# Copy the updated generated library code after filtering
COPY --from=side_a_generated /generated /generated

# Copy both the ROS1 and ROS2 packages and then determine which to compile
WORKDIR /catkin_ws
COPY ros1/ros1_bridge_grpc /catkin_ws/src/ros1_bridge_grpc

WORKDIR /colcon_ws
COPY ros2/ros2_bridge_grpc /colcon_ws/src/ros2/ros2_bridge_grpc

COPY common /common

ARG MESSAGE_PACKAGES
ENV MESSAGE_PACKAGES=${MESSAGE_PACKAGES}
RUN source /opt/ros/${SIDE_B_DISTRO}/setup.bash \
    && source ~/.profile && \
    if [ "${SIDE_B_DISTRO}" == "noetic" ]; then \
        cd /catkin_ws \
        && CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" catkin build --cmake-args -DCMAKE_BUILD_TYPE=Release \
        && echo "source /catkin_ws/devel/setup.bash" >> ~/.profile; \
    else \
        source /user_ws/install/setup.bash; \
        CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release \
        && echo "source /colcon_ws/install/setup.bash" >> ~/.profile; \
    fi


COPY docker/entrypoints/run_ros1_bridge.bash /entrypoints/run_ros1_bridge.bash
COPY docker/entrypoints/run_ros2_bridge.bash /entrypoints/run_ros2_bridge.bash
RUN chmod +x /entrypoints/run_ros1_bridge.bash && chmod +x /entrypoints/run_ros2_bridge.bash && \
    if [ "${SIDE_B_DISTRO}" == "noetic" ]; then \
        cp /entrypoints/run_ros1_bridge.bash /entrypoints/run_ros_bridge.bash; \
    else \
        cp /entrypoints/run_ros2_bridge.bash /entrypoints/run_ros_bridge.bash; \
    fi

# -------------------------------------------------------------------------------------------------
# SideA Bridge Dev
# -------------------------------------------------------------------------------------------------

FROM side_a_build AS side_a_dev

WORKDIR /colcon_ws

# Install core libraries
ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt upgrade -y \
    && apt install -y --no-install-recommends --no-install-suggests ros-dev-tools \
        nano \
        iputils-ping \
        python3-colcon-common-extensions \
        python3-rosdep \
        ros-${SIDE_A_DISTRO}-rmw-cyclonedds-cpp \
        ros-${SIDE_A_DISTRO}-tf2-tools \
        ros-${SIDE_A_DISTRO}-rqt-graph \
        ros-${SIDE_A_DISTRO}-rqt-tf-tree \
        ros-${SIDE_A_DISTRO}-rviz2 \
    && rm -rf /var/lib/apt/lists/*

# Terminal colors and .bashrc
RUN sed -i 's/#force_color_prompt=yes/force_color_prompt=yes/' "/root/.bashrc" \
    && sed -i 's/01;32m/01;36m/g; s/01;34m/01;35m/g' "/root/.bashrc" \
    && echo "source /opt/ros/${SIDE_A_DISTRO}/setup.bash" >> /root/.bashrc

# ROS logging format
ENV ROSCONSOLE_FORMAT='[${severity}] [${node} -> ${function}]: ${message}'

# -------------------------------------------------------------------------------------------------
# SideB Bridge Dev
# -------------------------------------------------------------------------------------------------

FROM side_b_build AS side_b_dev

WORKDIR /

# Install core libraries
ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt upgrade -y \
    && apt install -y --no-install-recommends --no-install-suggests ros-dev-tools \
        nano \
        iputils-ping \
        python3-rosdep \
        ros-${SIDE_B_DISTRO}-tf2-tools \
        ros-${SIDE_B_DISTRO}-rqt-graph \
        ros-${SIDE_B_DISTRO}-rqt-tf-tree \
        ros-${SIDE_B_DISTRO}-rviz \
    && rm -rf /var/lib/apt/lists/*

# Terminal colors and .bashrc
RUN sed -i 's/#force_color_prompt=yes/force_color_prompt=yes/' "/root/.bashrc" \
    && sed -i 's/01;32m/01;36m/g; s/01;34m/01;35m/g' "/root/.bashrc" \
    && echo "source /opt/ros/${SIDE_B_DISTRO}/setup.bash" >> /root/.bashrc

# ROS logging format
ENV ROSCONSOLE_FORMAT='[${severity}] [${node} -> ${function}]: ${message}'
