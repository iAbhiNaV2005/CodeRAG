/** @type {import('next').NextConfig} */
const apiProxyUrl = process.env.API_PROXY_URL || 'http://localhost:8080';

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiProxyUrl}/:path*`,
      },
    ]
  },
}

export default nextConfig
