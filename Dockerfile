FROM ghcr.io/astral-sh/uv:bookworm-slim

# 使用清华 apt 镜像源加速
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources

# 安装系统 Python，避免 uv 从 GitHub 下载
# 1. 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev \
    libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev \
    tk-dev libexpat1-dev liblzma-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. 下载并编译 Python 3.14（替换为实际版本号）
ENV PYTHON_VERSION=3.12.0
RUN wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz && \
    tar -xzf Python-${PYTHON_VERSION}.tgz && \
    cd Python-${PYTHON_VERSION} && \
    ./configure --enable-optimizations --prefix=/usr/local && \
    make -j8 && \
    make altinstall && \
    cd .. && rm -rf Python-${PYTHON_VERSION} Python-${PYTHON_VERSION}.tar.gz

# 3. 验证
RUN /usr/local/bin/python3.12 --version  # 应输出 Python 3.14.2
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 复制项目文件
COPY . .

# 使用系统 Python 和镜像源
ENV UV_PYTHON="/usr/local/bin/python3.12"
ENV UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
RUN uv sync

CMD ["uv", "run", "start_proxy.py"]
