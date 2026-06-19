/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://100.57.90.44:8080/:path*', // Proxy to your AWS server
      },
    ]
  },
}

export default nextConfig