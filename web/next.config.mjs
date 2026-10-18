/** @type {import('next').NextConfig} */
if (process.env.VERCEL === '1') {
  for (const key of ['NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_SUPABASE_URL']) {
    if (!process.env[key]?.startsWith('https://')) throw new Error(`${key} must use HTTPS on Vercel`);
  }
  if (!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    throw new Error('NEXT_PUBLIC_SUPABASE_ANON_KEY is required on Vercel');
  }
}
const nextConfig = {
  async headers() {
    return [{
      source: '/:path*',
      headers: [
        {key: 'X-Content-Type-Options', value: 'nosniff'},
        {key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin'},
        {key: 'X-Frame-Options', value: 'DENY'},
        {key: 'Permissions-Policy', value: 'camera=(self), microphone=(), geolocation=()'},
      ],
    }];
  },
};

export default nextConfig;
