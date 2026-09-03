FROM node:22-alpine

WORKDIR /app

# Install dependencies first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Then the app itself. In docker-compose the source is bind-mounted over /app
# and node_modules is kept as an anonymous volume.
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
