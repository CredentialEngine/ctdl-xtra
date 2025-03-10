# From https://github.com/puppeteer/puppeteer/blob/main/docker/Dockerfile
FROM node:20

# Configure default locale (important for chrome-headless-shell).
ENV LANG=en_US.UTF-8

# Install latest chrome dev package and fonts to support major charsets (Chinese, Japanese, Arabic, Hebrew, Thai and a few others)
# Note: this installs the necessary libs to make the bundled version of Chrome that Puppeteer
# installs, work.
RUN apt-get update \
  && apt-get install -y wget gnupg \
  && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
  && sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] https://dl-ssl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
  && apt-get update \
  && apt-get install -y google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-khmeros fonts-kacst fonts-freefont-ttf libxss1 dbus dbus-x11 \
  --no-install-recommends \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r pptruser && useradd -rm -g pptruser -G audio,video pptruser

# Install pm2 for running the app
RUN npm install pm2 -g

# Install pnpm
RUN npm install pnpm -g

# Build the app
COPY client/package.json client/pnpm-lock.yaml /build/app/client/
COPY server/package.json server/pnpm-lock.yaml /build/app/server/
RUN (cd /build/app/client && pnpm install) & \
  (cd /build/app/server && pnpm install) & \
  wait

USER pptruser
RUN /build/app/server/node_modules/.bin/rebrowser-puppeteer browsers install chrome

USER root
COPY client/ /build/app/client
COPY common /build/app/common
COPY server/ /build/app/server
RUN (cd /build/app/client && pnpm run build) & \
  (cd /build/app/server && pnpm run build) & \
  wait

RUN cp -R /build/app/server /app
RUN cp -R /build/app/client/dist /app/public

WORKDIR /app

EXPOSE 3000
ENTRYPOINT [ "/app/entrypoint.sh" ]
CMD ["pm2-runtime", "/app/dist/src/server.js"]
