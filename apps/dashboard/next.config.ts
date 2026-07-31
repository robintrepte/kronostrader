import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@kronos/ui", "@kronos/shared-types"],
  output: "standalone",
};

export default nextConfig;
