import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const appDir = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.resolve(appDir, "../..");

const nextConfig: NextConfig = {
  transpilePackages: ["@smartfit/contracts"],
  // Bundle Node server + runtime dependencies for Cloud Run (monorepo-aware).
  output: "standalone",
  outputFileTracingRoot: monorepoRoot,
};

export default nextConfig;
