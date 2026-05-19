ARG BASE_IMAGE=996810415034.dkr.ecr.us-east-1.amazonaws.com/ctdl-xtra-sandbox/base:latest
FROM ${BASE_IMAGE}

COPY server/package.json server/pnpm-lock.yaml server/pnpm-workspace.yaml /build/app/server/
RUN cd /build/app/server && pnpm install

COPY server/ /build/app/server
COPY common/ /build/app/common
RUN cd /build/app/server && pnpm run build

RUN cp -R /build/app/server /app

WORKDIR /app

ENTRYPOINT [ "/app/entrypoint-worker.sh" ]
CMD ["pm2-runtime", "/app/dist/server/src/worker.js"]
