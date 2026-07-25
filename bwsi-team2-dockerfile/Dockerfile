# BWSI Team 2 — Maze Wargame Per-Level Container
# Ubuntu 22.04 LTS with SSH server and one user per maze level.
# The orchestrator script SSHes into a `level<N>` account on port 22;
# each level's home directory contains that level's challenge from
# Challenges_2, and only that level's own files (levelN cannot read
# levelM's home even though every level shares one container/password).

FROM ubuntu:22.04

# Avoid interactive prompts from apt during build.
ENV DEBIAN_FRONTEND=noninteractive

# build-essential is needed to compile the reversing/pwn challenge sources
# at image-build time — the binaries handed off by the challenge designers
# are macOS Mach-O and won't run on this Linux image.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openssh-server \
        bash \
        coreutils \
        findutils \
        grep \
        sed \
        gawk \
        build-essential \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Prepare sshd runtime dirs (sshd refuses to run with an empty /var/run/sshd).
RUN mkdir -p /var/run/sshd && \
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo "AllowUsers level1 level2 level3 level4 level5 level6" >> /etc/ssh/sshd_config && \
    /usr/sbin/sshd -t

# Create the per-level users and set the shared password. Each home
# directory is locked to mode 700 so one level account cannot read
# another level's challenge files, even though every level lives in the
# same container and shares this SSH password.
RUN for n in 1 2 3 4 5 6; do \
        useradd -m -s /bin/bash "level${n}" && \
        echo "level${n}:maze2024" | chpasswd && \
        chmod 700 "/home/level${n}"; \
    done

# Compile the reversing/pwn challenge sources once at build time.
# chal is deliberately built without stack protection or PIE, and with an
# executable stack, so the ret2win buffer overflow is reliably exploitable.
COPY challenges/src /opt/challenge-src
RUN gcc -O0 -o /opt/challenge-src/msg /opt/challenge-src/hckthn_msg2.c && \
    gcc -O0 -o /opt/challenge-src/mystery /opt/challenge-src/mystery.c && \
    gcc -O0 -fno-stack-protector -no-pie -z execstack \
        -o /opt/challenge-src/chal /opt/challenge-src/ret2win.c

# Level 1 — OSINT: identify the building and the year it was built.
COPY --chown=level1:level1 challenges/challenge1/README.txt challenges/challenge1/OSINT1.png /home/level1/

# Level 2 — reversing: decompile msg to recover the string it compares against.
COPY --chown=level2:level2 challenges/challenge2/README.txt /home/level2/README.txt
RUN cp /opt/challenge-src/msg /home/level2/msg && \
    chown level2:level2 /home/level2/msg && \
    chmod 755 /home/level2/msg

# Level 3 — steganography: openstego door.bmp, then decode the extracted text.
COPY --chown=level3:level3 challenges/challenge3/README.txt challenges/challenge3/door.bmp /home/level3/

# Level 4 — pwn/ret2win: flag.txt is gated behind a successful exploit.
# chal is setuid to a dedicated, login-less "ctf4" account that owns
# flag.txt (mode 400), so `cat flag.txt` as level4 fails with Permission
# denied — only win() (running as ctf4 via setuid) can read and print it.
RUN useradd -r -s /usr/sbin/nologin ctf4
COPY --chown=level4:level4 challenges/challenge4/README.txt /home/level4/README.txt
COPY --chown=level4:level4 challenges/src/ret2win.c /home/level4/ret2win.c
RUN cp /opt/challenge-src/chal /home/level4/chal && \
    printf 'HWM{Y0u_g0t_this!}\n' > /home/level4/flag.txt && \
    chown ctf4:ctf4 /home/level4/chal /home/level4/flag.txt && \
    chmod 4755 /home/level4/chal && \
    chmod 400 /home/level4/flag.txt

# Level 5 — reversing: reverse mystery's transform (hint: it's self-inverse).
COPY --chown=level5:level5 challenges/challenge5/README.txt /home/level5/README.txt
RUN cp /opt/challenge-src/mystery /home/level5/mystery && \
    chown level5:level5 /home/level5/mystery && \
    chmod 755 /home/level5/mystery

# Level 6 — forensics: recover the flag from HTTP traffic in capture.pcap.
COPY --chown=level6:level6 challenges/challenge6/README.txt challenges/challenge6/capture.pcap /home/level6/

RUN rm -rf /opt/challenge-src

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D", "-e"]
