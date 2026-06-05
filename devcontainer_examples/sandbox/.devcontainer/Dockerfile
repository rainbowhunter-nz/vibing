FROM mcr.microsoft.com/devcontainers/javascript-node:24

ARG USERNAME=node

# claude-code: invoked by `vibing devcontainer-runtime` as `claude -p ...`
RUN npm install -g @anthropic-ai/claude-code

USER ${USERNAME}
