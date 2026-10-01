import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // PGlite loads its WASM/data files via real filesystem paths at runtime;
  // bundling it rewrites that resolution and breaks (TypeError: "path"
  // argument must be of type string ... Received an instance of URL).
  // Keep it as a real require()/import, not bundled.
  serverExternalPackages: ["@electric-sql/pglite"],
};

export default nextConfig;
