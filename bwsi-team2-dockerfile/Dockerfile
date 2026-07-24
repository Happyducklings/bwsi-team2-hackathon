# BWSI Team 2 — Maze Wargame Per-Level Container
# Ubuntu 22.04 LTS with SSH server and one user per maze level.
# The orchestrator script SSHes into a `level<N>` account on port 22;
# each level's home directory contains the challenge layout to explore.

FROM ubuntu:22.04

# Avoid interactive prompts from apt during build.
ENV DEBIAN_FRONTEND=noninteractive

# Install OpenSSH server and a few utilities useful for early levels.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openssh-server \
        bash \
        coreutils \
        findutils \
        grep \
        sed \
        gawk \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Prepare sshd runtime dirs (sshd refuses to run with an empty /var/run/sshd).
RUN mkdir -p /var/run/sshd && \
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo "AllowUsers level1 level2 level3 level4 level5" >> /etc/ssh/sshd_config

# Shared password across all levels (per project convention).
# Change the value here to rotate the password.
ARG LEVEL_PASSWORD=maze2024
ENV LEVEL_PASSWORD=${LEVEL_PASSWORD}

# Create the per-level users, set the shared password, and lay out level1's
# challenge directory. Levels 2-5 are stubbed with empty homes for now so the
# Dockerfile is ready when their layouts are designed.
RUN for n in 1 2 3 4 5; do \
        useradd -m -s /bin/bash "level${n}" && \
        echo "level${n}:${LEVEL_PASSWORD}" | chpasswd; \
    done

# Level 1 challenge layout — a small directory tree with clues and notes.
# Add more files/dirs here as the team designs the actual challenges.
RUN mkdir -p /home/level1/chamber/start && \
    mkdir -p /home/level1/chamber/middle && \
    mkdir -p /home/level1/chamber/end && \
    echo "Welcome, traveller. You stand at the entrance of Level 1." \
        > /home/level1/chamber/start/WELCOME.txt && \
    echo "A riddle is hidden somewhere in this chamber. Find it." \
        > /home/level1/chamber/middle/CLUE.txt && \
    echo "Well done — you have reached the end of Level 1." \
        > /home/level1/chamber/end/SUCCESS.txt && \
    echo "The password for the next door is: not-a-real-password" \
        > /home/level1/chamber/end/REWARD.txt && \
    chown -R level1:level1 /home/level1/chamber && \
    chmod 755 /home/level1 && \
    chmod -R 755 /home/level1/chamber

# Level 2-5 placeholder homes so SSH logins work but show "no challenges yet".
RUN for n in 2 3 4 5; do \
        echo "Level ${n} is under construction. Check back soon." \
            > "/home/level${n}/README.txt" && \
        chown "level${n}:level${n}" "/home/level${n}/README.txt"; \
    done

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D", "-e"]
