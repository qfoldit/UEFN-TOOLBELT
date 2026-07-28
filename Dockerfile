FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive \
    GLAMA_VERSION="1.0.0" \
    PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git && curl -fsSL https://deb.nodesource.com/setup_26.x | bash - && apt-get install -y --no-install-recommends nodejs && npm install -g mcp-proxy@6.4.3 pnpm@10.14.0 && node --version && curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="/usr/local/bin" sh && uv python install 3.14 --default --preview && ln -s $(uv python find) /usr/local/bin/python && python --version && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
WORKDIR /app
RUN git clone https://github.com/qfoldit/UEFN-TOOLBELT . && git checkout 45bab87909f55f04ccc6d310d50bb0687c1cbef5
ENV PATH="/app/node_modules/.bin:$PATH"
CMD ["mcp-proxy","--"]
