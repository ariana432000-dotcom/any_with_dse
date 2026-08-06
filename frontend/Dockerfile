# Simple, single-stage-runtime Dockerfile for the AInvest frontend.
# For a smaller production image you can switch to Next's `output: "standalone"`
# mode later — this keeps things simple and matches how `npm run build && npm run start`
# behaves locally, which is what most local/dev deployments of this app need.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

# Baked in at build time so a plain `docker build` still works; override with
# --build-arg or the NEXT_PUBLIC_API_URL env var in docker-compose.yml.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
