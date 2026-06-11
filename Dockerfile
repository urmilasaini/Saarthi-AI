FROM python:3.11-slim

LABEL org.opencontainers.image.title="Saarthi AI" \
      org.opencontainers.image.description="Proactive commute-planning agent for Lucknow, built for the Google Cloud Rapid Agent Hackathon MongoDB Partner Track." \
      org.opencontainers.image.authors="Saksham Pathak, Aishrica Dhiman, Sameer Singh, Urmila Saini" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.url="https://urmilasaini-saarthiai.hf.space/" \
      org.opencontainers.image.source="https://github.com/parthmax2/saarthi-ai"

# Node.js is required by the MongoDB MCP server.
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Pre-install the MongoDB MCP server so chat requests do not download it.
RUN npm install -g mongodb-mcp-server@latest

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces expects port 7860
ENV PORT=7860
ENV MONGODB_MCP_COMMAND=mongodb-mcp-server
ENV MONGODB_MCP_ARGS=--readOnly
ENV MONGODB_MCP_READ_ONLY=true
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
