FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG USERNAME=vscode
ARG NVM_VERSION=v0.40.1
ARG PNPM_VERSION=11.3.0

ENV NVM_DIR=/home/${USERNAME}/.nvm
ENV NVM_SYMLINK_CURRENT=true
ENV PATH=${NVM_DIR}/current/bin:/home/${USERNAME}/.local/bin:${PATH}

RUN install -m 0755 -d /etc/apt/keyrings \
   && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
   && chmod a+r /etc/apt/keyrings/docker.gpg \
   && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" \
   > /etc/apt/sources.list.d/docker.list \
   && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
   | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
   && chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
   && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
   > /etc/apt/sources.list.d/github-cli.list \
   && apt-get update \
   && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin docker-compose-plugin gh \
   && rm -rf /var/lib/apt/lists/*

USER ${USERNAME}

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash \
   && . ${NVM_DIR}/nvm.sh \
   && nvm install --lts \
   && nvm alias default 'lts/*' \
   && nvm use default

RUN . ${NVM_DIR}/nvm.sh && npx -y playwright@latest install-deps

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN npm install -g @anthropic-ai/claude-code \
   && npm install --global corepack@latest \
   && corepack enable pnpm \
   && corepack install -g pnpm@${PNPM_VERSION}

RUN npx -y playwright@latest install

RUN echo '[ -f /workspaces/vibing/.devcontainer/bash_preference.bash ] && . /workspaces/vibing/.devcontainer/bash_preference.bash' >> /home/${USERNAME}/.bashrc
