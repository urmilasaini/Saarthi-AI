FROM python:3.11-slim

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
