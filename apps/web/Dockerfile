FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json /app/
RUN npm ci

COPY public /app/public
COPY src /app/src
COPY next.config.ts tsconfig.json eslint.config.mjs next-env.d.ts /app/

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-p", "3000"]

