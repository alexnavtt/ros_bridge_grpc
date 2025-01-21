FROM ros:noetic

# User configuration
ARG USERNAME
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# -------------------------------------------------------------------------------------------------
# SETUP USER --------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Switch to the non-root user
USER $USERNAME
RUN sudo chown -R $USERNAME /home/$USERNAME

RUN echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc

ENV ROSCONSOLE_FORMAT '[${severity}] [${node} -> ${function}]: ${message}'

# -------------------------------------------------------------------------------------------------
# SETUP ROS1 --------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------

RUN sudo apt update && sudo apt upgrade -y

RUN sudo apt install -y \
        ros-noetic-std-msgs \
        ros-noetic-geometry-msgs \
        ros-noetic-sensor-msgs \
        ros-noetic-nav-msgs \
        ros-noetic-tf2-msgs

# -------------------------------------------------------------------------------------------------
# SETUP GRPC --------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------

WORKDIR /home/${USERNAME}
RUN sudo chown -R ${USERNAME} /home/${USERNAME}
RUN sudo apt install -y build-essential autoconf libtool pkg-config git

RUN export MY_INSTALL_DIR=$HOME/.local \
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
# SETUP BRIDGE DEPENDENCIES -----------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------

RUN sudo apt install -y python3-pip python3-catkin-tools \
    && python3 -m pip install proto_schema_parser

# -------------------------------------------------------------------------------------------------
# SETUP USER INTERFACE ----------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------

# Set up terminal and bashrc
RUN sed -i 's/#force_color_prompt=yes/force_color_prompt=yes/' "/home/${USERNAME}/.bashrc" \
    && sed -i 's/01;32m/01;36m/g; s/01;34m/01;35m/g' "/home/${USERNAME}/.bashrc"
