ARG ROS1_DISTRO=noetic
ARG ROS2_DISTRO=humble

# -------------------------------------------------------------------------------------------------
# GRPC
# -------------------------------------------------------------------------------------------------

# Build gRPC for use in both sides of the bridge
FROM ubuntu:jammy AS grpc_base

RUN apt update \
    && apt install -y \
        git \
        cmake \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN export MY_INSTALL_DIR=/install \
    && mkdir -p $MY_INSTALL_DIR \
    && export PATH="$MY_INSTALL_DIR/bin:$PATH" \
    && git clone --recurse-submodules -b v1.66.0 --depth 1 --shallow-submodules https://github.com/grpc/grpc \
    && cd grpc \
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
# ROS2
# -------------------------------------------------------------------------------------------------

FROM ros:${ROS2_DISTRO}-ros-base AS ros2_base

ARG ROS2_DISTRO

SHELL ["/bin/bash", "-lc"]
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install cyclonedds
RUN apt update \
    && apt install -y ros-${ROS2_DISTRO}-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies and build all message types
ARG SYSTEM_PACKAGES=""
RUN apt update && \
    apt install -y python3-pip && \
    if [ ! -z "${SYSTEM_PACKAGES}" ]; then \
        for pkg in ${SYSTEM_PACKAGES}; do\
            apt install -y ros-${ROS2_DISTRO}-$pkg; \
        done; \
    fi && \
    rm -rf /var/lib/apt/lists/*

    
# Copy user packages into the image
COPY docker/mapped /user_ws/src/
    
# Clone git-based user packages
ARG USER_REPOS=""
WORKDIR /user_ws/src
RUN --mount=type=ssh \
    if [ ! -z "${USER_REPOS}" ]; then\
        echo "${USER_REPOS}" | tr ";" "\n" | while read -r repo; do \
            [[ -z "$repo" ]] && continue; \
            git clone $repo; \
        done;\
    fi

# Build user packages
WORKDIR /user_ws
RUN rosdep update \
    && apt update \
    && rosdep install --from-paths /user_ws/src -i -y \
    && rm -rf /var/lib/apt/lists*
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash && colcon build && echo "source /user_ws/install/setup.bash" >> ~/.profile

# Copy the generated protoc and gRPC libraries
COPY --from=grpc_base /install /install
ENV PATH="/install/bin:$PATH"

# Generate proto files
ARG ALLOWED_TYPES=""
COPY scripts/build_bridge_ros2.py /scripts/build_bridge_ros2.py
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash \
    && source /user_ws/install/setup.bash \
    && mkdir /generated \
    && python3 /scripts/build_bridge_ros2.py /generated ${ALLOWED_TYPES}

# Generate C++ source code to translate between proto and ROS
COPY scripts/generate_cpp_conversion_code.py /scripts/generate_cpp_conversion_code.py
RUN pip install proto-schema-parser
RUN python3 /scripts/generate_cpp_conversion_code.py /generated

# Add the ROS2 package and compile
WORKDIR /colcon_ws
COPY ros2 /colcon_ws/src/ros2
COPY common /common

ARG MESSAGE_PACKAGES
ENV MESSAGE_PACKAGES=${MESSAGE_PACKAGES}
RUN source /opt/ros/${ROS2_DISTRO}/setup.bash \
    && source ~/.profile \
    && echo "$CMAKE_PREFIX_PATH" \
    && CMAKE_PREFIX_PATH="/install:$CMAKE_PREFIX_PATH" colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && echo "source /colcon_ws/install/setup.bash" >> ~/.profile

# -------------------------------------------------------------------------------------------------
# ROS1
# -------------------------------------------------------------------------------------------------