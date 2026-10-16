# The viewer as a static site behind nginx, with the extract output (data/out) baked in.
#
#   docker build -t xtra-reviewer-mockup .
#   docker run --rm -p 8080:8080 xtra-reviewer-mockup      # http://localhost:8080
#
# The build stage runs on the build machine's own architecture, since its output is static files;
# only the nginx stage is built for the target platform.
FROM --platform=$BUILDPLATFORM node:24-alpine AS build
WORKDIR /app
COPY viewer/package.json viewer/package-lock.json viewer/
RUN cd viewer && npm ci
COPY viewer/ viewer/
# vite.config.ts copies ../data/out into dist/data when the build closes.
COPY data/out/ data/out/
RUN cd viewer && npm run build

# Listens on 8080 and runs as a non-root user.
FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY --from=build /app/viewer/dist/ /usr/share/nginx/html/
EXPOSE 8080
