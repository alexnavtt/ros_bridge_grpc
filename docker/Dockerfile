ARG ROS1_DISTRO=noetic
ARG ROS2_DISTRO=humble
ARG ROS2_UBUNTU=jammy

# -------------------------------------------------------------------------------------------------
# GRPC GIT
# ------------------------------------------------------------------------------------------------- 
    
FROM alpine/git AS grpc_base
RUN cd / && git clone --recurse-submodules -b v1.66.0 --depth 1 --shallow-submodules https://github.com/grpc/grpc

# -------------------------------------------------------------------------------------------------
# GRPC ROS2
# -------------------------------------------------------------------------------------------------

# Build gRPC for use in both sides of the bridge
FROM ubuntu:${ROS2_UBUNTU} AS grpc_base_ros2

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt install -y \
        git \
        cmake \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY --from=grpc_base /grpc /grpc
RUN export MY_INSTALL_DIR=/install \
    && mkdir -p $MY_INSTALL_DIR \
    && cd /grpc \
    && mkdir -p cmake/build \
    && cd cmake/build \
    && cmake -DgRPC_INSTALL=ON \
        -DgRPC_BUILD_TESTS=OFF \
        -DCMAKE_CXX_STANDARD=17 \
        -DCMAKE_INSTALL_PREFIX=$MY_INSTALL_DIR \
        ../.. \
    && make -j 8 \
    && make install

# -------------------------------------------------------------------------------------------------
# GRPC ROS1
# -------------------------------------------------------------------------------------------------

# Build gRPC for use in both sides of the bridge
FROM ubuntu:focal AS grpc_base_ros1

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt install -y \
        git \
        cmake \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY --from=grpc_base /grpc /grpc
RUN export MY_INSTALL_DIR=/install \
    && mkdir -p $MY_INSTALL_DIR \
    && cd /grpc \
    && mkdir -p cmake/build \
    && cd cmake/build \
    && rm -rf * \
    && export MAKE=/usr/bin/make \
    && cmake -DgRPC_INSTALL=ON \
        -DgRPC_BUILD_TESTS=OFF \
        -DCMAKE_CXX_STANDARD=17 \
        -DCMAKE_INSTALL_PREFIX=$MY_INSTALL_DIR \
        ../.. \
    && make -j 8 \
    && make install

# -------------------------------------------------------------------------------------------------
# ROS2 Generate
# -------------------------------------------------------------------------------------------------

FROM ros:${ROS2_DISTRO}-ros-base AS ros2_base

ARG ROS2_DISTRO

SHELL ["/bin/bash", "-lc"]
ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install cyclonedds
RUN apt update \
    && apt install -y ros-${ROS2_DISTRO}-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# Install system message types
ARG SYSTEM_PACKAGES=""
RUN apt update && \
    apt install -y python3-pip openssh-client && \
    if [ ! -z "${SYSTEM_PACKAGES}" ]; then \
        for pkg in ${SYSTEM_PACKAGES}; do\
            apt install -y ros-${ROS2_DISTRO}-$pkg; \
        done; \
    fi && \
    rm -rf /var/lib/apt/lists/*

    
# Copy user packages into the image
COPY docker/mapped/ros2 /user_ws/src/
    
# Clone git-based user packages
ARG USER_ROS2_REPOS=""
ARG GIT_RECLONE=1
WORKDIR /user_ws/src
RUN --mount=type=ssh \
    mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    if [ ! -z "${USER_ROS2_REPOS}" ]; then\
        echo "${USER_ROS2_REPOS}" | tr ";" "\n" | while read -r repo; do \
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
    && source /opt/ros/${ROS2_DISTRO}/setup.bash && \
    for pkg in ${CUSTOM_PACKAGES}; do \
        pkg_path=$(colcon list | awk -v pkg_name="$pkg" '$1 == pkg_name {print $2}'); \
        rosdep install --from-paths "$pkg_path" -i -y; \
    done \
    && rm -rf /var/lib/apt/lists*
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash && colcon build --packages-up-to ${CUSTOM_PACKAGES} && echo "source /user_ws/install/setup.bash" >> ~/.profile

# Copy the generated protoc and gRPC libraries
COPY --from=grpc_base_ros2 /install /install
ENV PATH="/install/bin:$PATH"

# Generate proto files
ARG ALLOWED_TYPES=""
COPY scripts/build_bridge_ros2.py /scripts/build_bridge_ros2.py
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash \
    && source /user_ws/install/setup.bash \
    && mkdir /generated \
    && python3 /scripts/build_bridge_ros2.py /generated ${ALLOWED_TYPES}

# -------------------------------------------------------------------------------------------------
# ROS1 Generate
# -------------------------------------------------------------------------------------------------

FROM ros:${ROS1_DISTRO}-ros-base AS ros1_base
ARG ROS1_DISTRO

SHELL ["/bin/bash", "-lc"]
ARG DEBIAN_FRONTEND=noninteractive

# Fix ROS1 apt key issues
RUN mkdir -p /etc/apt/keyrings \
    && sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list' \
    && curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -

# Install system message types
ARG SYSTEM_PACKAGES=""
RUN apt update && \
    apt install -y git python3-pip python3-catkin-tools openssh-client && \
    if [ ! -z "${SYSTEM_PACKAGES}" ]; then \
        for pkg in ${SYSTEM_PACKAGES}; do\
            apt install -y ros-${ROS1_DISTRO}-$pkg; \
        done; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# Create a catkin workspace
WORKDIR /user_ws
RUN mkdir -p src && source /opt/ros/${ROS1_DISTRO}/setup.bash && catkin build

# Copy user packages into the image
COPY docker/mapped/ros1 /user_ws/src/
    
# Clone git-based user packages
ARG USER_ROS1_REPOS=""
ARG GIT_RECLONE=1
WORKDIR /user_ws/src
RUN --mount=type=ssh \
    mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && \
    if [ ! -z "${USER_ROS1_REPOS}" ]; then\
        echo "${USER_ROS1_REPOS}" | tr ";" "\n" | while read -r repo; do \
            if [ -n "$repo" ]; then \
                echo "Cloning $repo"; \
                eval "git clone $repo"; \
            fi; \
        done;\
    fi

# Build user packages
ARG CUSTOM_PACKAGES=""
WORKDIR /user_ws
RUN rosdep update \
    && apt update \
    && source /opt/ros/${ROS1_DISTRO}/setup.bash && \
    for pkg in ${CUSTOM_PACKAGES}; do \
        pkg_path=$(catkin locate "$pkg"); \
        rosdep install --from-paths "$pkg_path" -i -y; \
    done \
    && rm -rf /var/lib/apt/lists*
RUN source /opt/ros/${ROS1_DISTRO}/setup.bash && catkin build ${CUSTOM_PACKAGES} && echo "if [ -f '/user_ws/devel/setup.bash' ]; then source /user_ws/devel/setup.bash; fi" >> ~/.profile

# Copy the generated protoc and gRPC libraries
COPY --from=grpc_base_ros1 /install /install
ENV PATH="/install/bin:$PATH"

# Copy generated library code
COPY --from=ros2_base /generated /generated

# Install dependencies for the script
RUN pip install proto-schema-parser

# Verify generated proto files
ARG ALLOWED_TYPES=""
ARG COMPAT_OVERRIDES=""
COPY scripts/build_bridge_ros1.py /scripts/build_bridge_ros1.py
RUN source /opt/ros/${ROS1_DISTRO}/setup.bash \
    && source ~/.profile \
    && COMPAT_OVERRIDES=${COMPAT_OVERRIDES} python3 /scripts/build_bridge_ros1.py /generated

# -------------------------------------------------------------------------------------------------
# ROS2 Generate Stage 2
# -------------------------------------------------------------------------------------------------

FROM ros2_base AS ros2_generated

# Copy the updated generated library code after filtering
RUN rm -rf /generated
COPY --from=ros1_base /generated /generated

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
RUN python3 /scripts/generate_cpp_conversion_code.py /generated

# -------------------------------------------------------------------------------------------------
# ROS2 Build
# -------------------------------------------------------------------------------------------------

FROM ros2_generated AS ros2_build

# Add the ROS2 package and compile
WORKDIR /colcon_ws
COPY ros2 /colcon_ws/src/ros2
COPY common /common

ARG MESSAGE_PACKAGES
ENV MESSAGE_PACKAGES=${MESSAGE_PACKAGES}
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash \
    && source ~/.profile \
    && CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && echo "source /colcon_ws/install/setup.bash" >> ~/.profile

COPY docker/entrypoints/run_ros2_bridge.bash /entrypoints/run_ros2_bridge.bash
RUN chmod +x /entrypoints/run_ros2_bridge.bash

# -------------------------------------------------------------------------------------------------
# ROS1 Build
# -------------------------------------------------------------------------------------------------

FROM ros1_base AS ros1_build

# Copy the updated generated library code after filtering
COPY --from=ros2_generated /generated /generated

# Add the ROS1 package and compile
WORKDIR /catkin_ws
COPY ros1 /catkin_ws/src/ros1
COPY common /common

ARG MESSAGE_PACKAGES
ENV MESSAGE_PACKAGES=${MESSAGE_PACKAGES}
RUN source /opt/ros/${ROS1_DISTRO}/setup.bash \
    && source ~/.profile \
    && catkin config --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" catkin build --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && echo "source /catkin_ws/devel/setup.bash" >> ~/.profile

COPY docker/entrypoints/run_ros1_bridge.bash /entrypoints/run_ros1_bridge.bash
RUN chmod +x /entrypoints/run_ros1_bridge.bash

# -------------------------------------------------------------------------------------------------
# ROS2 Bridge Dev
# -------------------------------------------------------------------------------------------------

FROM ros2_build AS ros2_bridge_dev

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
        ros-${ROS2_DISTRO}-rmw-cyclonedds-cpp \
        ros-${ROS2_DISTRO}-tf2-tools \
        ros-${ROS2_DISTRO}-rqt-graph \
        ros-${ROS2_DISTRO}-rqt-tf-tree \
        ros-${ROS2_DISTRO}-rviz2 \
    && rm -rf /var/lib/apt/lists/*

# Terminal colors and .bashrc
RUN sed -i 's/#force_color_prompt=yes/force_color_prompt=yes/' "/root/.bashrc" \
    && sed -i 's/01;32m/01;36m/g; s/01;34m/01;35m/g' "/root/.bashrc" \
    && echo "source /opt/ros/${ROS2_DISTRO}/setup.bash" >> /root/.bashrc

# ROS logging format
ENV ROSCONSOLE_FORMAT '[${severity}] [${node} -> ${function}]: ${message}'

# -------------------------------------------------------------------------------------------------
# ROS1 Bridge Dev
# -------------------------------------------------------------------------------------------------

FROM ros1_build AS ros1_bridge_dev

WORKDIR /catkin_ws

# Install core libraries
ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt upgrade -y \
    && apt install -y --no-install-recommends --no-install-suggests ros-dev-tools \
        nano \
        iputils-ping \
        python3-rosdep \
        ros-${ROS1_DISTRO}-tf2-tools \
        ros-${ROS1_DISTRO}-rqt-graph \
        ros-${ROS1_DISTRO}-rqt-tf-tree \
        ros-${ROS1_DISTRO}-rviz \
    && rm -rf /var/lib/apt/lists/*

# Terminal colors and .bashrc
RUN sed -i 's/#force_color_prompt=yes/force_color_prompt=yes/' "/root/.bashrc" \
    && sed -i 's/01;32m/01;36m/g; s/01;34m/01;35m/g' "/root/.bashrc" \
    && echo "source /opt/ros/${ROS1_DISTRO}/setup.bash" >> /root/.bashrc

# ROS logging format
ENV ROSCONSOLE_FORMAT='[${severity}] [${node} -> ${function}]: ${message}'
