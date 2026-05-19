ARG BASE_IMAGE=996810415034.dkr.ecr.us-east-1.amazonaws.com/ctdl-xtra-test/base:latest
FROM ${BASE_IMAGE}

ENV VITE_API_URL="$VITE_API_URL"

COPY client/package.json client/pnpm-lock.yaml client/pnpm-workspace.yaml /build/app/client/
COPY server/package.json server/pnpm-lock.yaml server/pnpm-workspace.yaml /build/app/server/
RUN (cd /build/app/client && pnpm install) & \
  (cd /build/app/server && pnpm install) & \
  wait

COPY client/ /build/app/client
COPY common/ /build/app/common
COPY server/ /build/app/server
RUN (cd /build/app/client && pnpm run build) & \
  (cd /build/app/server && pnpm run build) & \
  wait

RUN cp -R /build/app/server /app
RUN cp -R /build/app/client/dist /app/public

WORKDIR /app

EXPOSE 3000
ENTRYPOINT [ "/app/entrypoint.sh" ]
CMD ["pm2-runtime", "/app/dist/server/src/server.js"]
