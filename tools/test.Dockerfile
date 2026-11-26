FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential make python3 libgl-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
    libasound2-dev xvfb libgl1-mesa-dri libglx-mesa0 libasound2t64 && rm -rf /var/lib/apt/lists/*
