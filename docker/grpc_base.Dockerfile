ARG UBUNTU_DISTRO=jammy

# -------------------------------------------------------------------------------------------------
# GRPC GIT
# ------------------------------------------------------------------------------------------------- 
    
FROM alpine/git AS grpc_base
RUN cd / && git clone --recurse-submodules -b v1.66.0 --depth 1 --shallow-submodules https://github.com/grpc/grpc

# -------------------------------------------------------------------------------------------------
# GRPC BUILD
# -------------------------------------------------------------------------------------------------

# Build gRPC for use in both sides of the bridge
FROM ubuntu:${UBUNTU_DISTRO} AS grpc_base_ros2

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
    && export MAKE=/usr/bin/make \
    && cmake -DgRPC_INSTALL=ON \
        -DgRPC_BUILD_TESTS=OFF \
        -DCMAKE_CXX_STANDARD=17 \
        -DCMAKE_INSTALL_PREFIX=$MY_INSTALL_DIR \
        ../.. \
    && make -j 8 \
    && make install
