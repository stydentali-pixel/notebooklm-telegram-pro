FROM node:22-bookworm-slim AS app

WORKDIR /app

RUN apt-get update && apt-get install -y \
    openssl \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
COPY prisma ./prisma

RUN npm install --include=dev

COPY . .

RUN npx prisma generate
RUN npx tsc -p tsconfig.json

EXPOSE 3000

CMD ["sh", "-c", "npx prisma db push && npm run start"]
