// Optional Cloudflare Worker gateway for Telegram -> Railway.
// Deploy only after Railway is working.
// Environment variables in Cloudflare Worker:
// RAILWAY_WEBHOOK_URL = https://your-app.up.railway.app/telegram/webhook
// TELEGRAM_WEBHOOK_SECRET = same secret as Railway
// GATEWAY_SECRET = optional secret for /health

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/health') {
      const secret = url.searchParams.get('secret') || '';
      if (env.GATEWAY_SECRET && secret !== env.GATEWAY_SECRET) {
        return new Response('Forbidden', { status: 403 });
      }
      return Response.json({ ok: true, gateway: 'cloudflare-worker' });
    }

    if (url.pathname !== '/telegram/webhook') {
      return new Response('Not found', { status: 404 });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const telegramSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (env.TELEGRAM_WEBHOOK_SECRET && telegramSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('Forbidden', { status: 403 });
    }

    const body = await request.text();
    const upstream = await fetch(env.RAILWAY_WEBHOOK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Bot-Api-Secret-Token': env.TELEGRAM_WEBHOOK_SECRET || telegramSecret,
      },
      body,
    });

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('Content-Type') || 'application/json' },
    });
  },
};
