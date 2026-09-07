ARG UBUNTU_DISTRO=jammy

# -------------------------------------------------------------------------------------------------
# Build gRPC for use in either side of the bridge
# ------------------------------------------------------------------------------------------------- 

FROM ubuntu:${UBUNTU_DISTRO} AS grpc_base

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update \
    && apt install -y \
        git \
        cmake \
        build-essential \
        autoconf \
        libtool \
        pkg-config \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN cd / && git clone --recurse-submodules -b v1.66.0 --depth 1 --shallow-submodules https://github.com/grpc/grpc

RUN PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --user cmake==3.24

RUN export MY_INSTALL_DIR=/install \
    && mkdir -p $MY_INSTALL_DIR \
    && cd /grpc \
    && mkdir -p cmake/build \
    && cd cmake/build \
    && export MAKE=/usr/bin/make \
    && ~/.local/bin/cmake -DgRPC_INSTALL=ON \
        -DgRPC_BUILD_TESTS=OFF \
        -DCMAKE_CXX_STANDARD=14 \
        -DCMAKE_INSTALL_PREFIX=$MY_INSTALL_DIR \
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        -DCMAKE_CXX_FLAGS="-include cstdint" \
        ../.. \
    && make -j 8 \
    && make install
