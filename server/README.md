# xTRA Server

This is the backend server for [CTDL xTRA](../README.md). It's built with
Fastify and provides the API endpoints and background processing capabilities
for the application.

## Components

- **Dependencies and tooling**: pnpm, TypeScript, vitest
- **API server**: Fastify and tRPC
- **Background processing**: BullMQ
- **Web scraping**: Puppeteer
- **Email**: React Email for templating and Nodemailer for sending
- **Database**: PostgreSQL with Drizzle ORM
- **Cache**: Redis
- **Error monitoring**: Airbrake

## Setup

1. Install [node.js](https://nodejs.org/en) (20+) (using [nvm](https://github.com/nvm-sh/nvm) is a plus) and [pnpm](https://pnpm.io/)

2. Install dependencies:

```bash
pnpm install
pnpm dlx puppeteer browsers install

# or specific version
pnpm dlx puppeteer browsers install chrome@130.0.6723.58
```

3. Set up environment variables:

```bash
cp .env.example .env # edit your env vars in .env
```

Generate keys required for [secure-session](https://github.com/fastify/fastify-secure-session) encryption (32 bytes - 64 hex encoded characters)
```bash
pnpm exec secure-session | xxd -p -c 0
```
Use generated key in the `COOKIE_KEY` env variable.

## Development

Run the development server:

```bash
pnpm run dev
```

Start the background worker:

```bash
pnpm run dev:worker
```

Run the email preview server:

```bash
pnpm run dev:email
```

Docker:
```bash
docker run --env=POSTGRES_PASSWORD=pass -p 5432:5432 -d postgres:13-alpine
docker run -p 6379:6379 -d redis
```

## Database

The application uses PostgreSQL with Drizzle ORM for database management.

Generate database migrations:

```bash
pnpm run db:generate
```

Apply migrations:

```bash
pnpm run db:migrate
```

To seed a development user, use `src/createUser.ts`:

## Testing

Run tests:
```bash
pnpm run test
```

Note that tests currently act more like model evals than standard
unit/integration tests. They will call the real OpenAI API.
