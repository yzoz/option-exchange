# Веб-слой Node/Express (bin/www) — отдаёт страницы и статику.
# Образ используется compose-профилем «app» (полный стек в контейнерах).
FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY . .

EXPOSE 3000
CMD ["node", "./bin/www"]
