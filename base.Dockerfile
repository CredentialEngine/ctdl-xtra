FROM node:20

ENV LANG=en_US.UTF-8

RUN apt-get update \
  && apt-get install -y wget gnupg \
  && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
  && sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] https://dl-ssl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
  && apt-get update \
  && apt-get install -y google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-khmeros fonts-kacst fonts-freefont-ttf libxss1 dbus dbus-x11 \
  --no-install-recommends \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r pptruser && useradd -rm -g pptruser -G audio,video pptruser

RUN npm install -g pm2 pnpm rebrowser-puppeteer@23.6.101

USER pptruser
RUN rebrowser-puppeteer browsers install chrome
RUN rebrowser-puppeteer browsers install chrome-headless-shell
USER root
