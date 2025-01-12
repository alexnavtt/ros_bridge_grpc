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
