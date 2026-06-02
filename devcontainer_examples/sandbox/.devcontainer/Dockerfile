FROM mcr.microsoft.com/devcontainers/javascript-node:24

ARG USERNAME=node
ENV PATH=/home/${USERNAME}/.local/bin:${PATH}

# claude-code: invoked by `vibing devcontainer-runtime` as `claude -p ...`
RUN npm install -g @anthropic-ai/claude-code

USER ${USERNAME}

# uv: used to install the vibing CLI into an isolated tool env with its own Python 3.13
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# vibing: provides `vibing devcontainer-runtime`, launched by the host runtime via `devcontainer exec`.
# Shipped as a prebuilt wheel inside the build context (rebuild with scripts/refresh-wheel.sh after source changes).
COPY wheels/*.whl /tmp/wheels/
RUN uv tool install --python 3.13 --from "$(ls /tmp/wheels/*.whl)" vibing