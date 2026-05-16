This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## Making It Public

This app has two deployable pieces:

- The Next.js frontend.
- The FastAPI backend that talks to YouTube Music.

For the frontend, set this environment variable wherever you deploy it:

```txt
NEXT_PUBLIC_API_URL=https://your-api-host.example.com
```

For the backend, set these environment variables:

```txt
FRONTEND_ORIGINS=https://your-frontend-host.example.com
YTMUSIC_AUTH_FILE=/etc/secrets/headers_auth.json
```

The backend start command is:

```bash
python backend/start.py
```

Do not commit `backend/headers_auth.json`. It contains private YouTube Music auth data and should be uploaded to your backend host as a secret file.

On Render, deploy the backend as a Python Web Service:

```txt
Root Directory: leave blank
Build Command: pip install -r requirements.txt
Start Command: python backend/start.py
```

Add `headers_auth.json` as a Render secret file at:

```txt
/etc/secrets/headers_auth.json
```

After deploying, open `/health` first. It should load even if the auth file is missing. Then open `/albums` to test YouTube Music access.
