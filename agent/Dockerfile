# The sandbox the agent runs inside. One trial = one fresh container.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    strace git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# A real coding agent gets installed here. Examples (uncomment what you use):
#   pip install aider-chat
#   npm i -g @anthropic-ai/claude-code   (needs node)
# The mock agent needs nothing extra.
RUN pip install --no-cache-dir pytest requests

WORKDIR /work
COPY harness/ /harness/
COPY scenario/ /scenario/

# strace needs ptrace; granted via cap_add in compose, not here.
ENTRYPOINT ["python3", "/harness/entrypoint.py"]
