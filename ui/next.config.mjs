/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://34.238.209.25:8080/:path*`,
      },
    ]
  },
}

export default nextConfig
