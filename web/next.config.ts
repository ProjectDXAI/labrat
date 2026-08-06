import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev server binds 0.0.0.0 so the explorer is reachable from other machines on this
  // LAN. Next then treats any host that is not the bind address as cross-origin and
  // refuses to serve its own dev chunks, which fails as a page that renders its header,
  // loads its data, and never hydrates. Naming the hosts that may reach it fixes that.
  //
  // These are loopback and RFC1918 ranges only. Nothing here is reachable from outside
  // the local network, and this setting has no effect on a production build.
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    "10.0.0.96",
    "*.local",
    "10.0.0.*",
    "192.168.*.*",
    "172.16.*.*",
  ],
};

export default nextConfig;
