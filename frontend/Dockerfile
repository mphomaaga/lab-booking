# Frontend image: build with Node LTS, serve dist/ with nginx. Build context is frontend/.

FROM node:lts-alpine AS build
WORKDIR /app

# VITE_* values are baked into the bundle at build time (they are not secrets).
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_USE_MOCK_API=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_USE_MOCK_API=$VITE_USE_MOCK_API

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
