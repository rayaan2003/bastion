import { load as loadYaml } from "js-yaml";
import { NextRequest, NextResponse } from "next/server";
import { savePolicyVersion } from "@/lib/policy";

// Session-protected (proxy.ts matches /policy/:path*) - this is for the
// human reviewer's form submission on /policy, not the SDK.
//
// Only validates that the text is syntactically valid YAML. Deeper
// semantic validation (unknown condition type, missing rule fields, etc.)
// happens Python-side in bastion.config when the SDK actually loads it
// - duplicating that rule-schema logic in TypeScript isn't worth the
// maintenance burden of keeping two implementations in sync.
export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const yamlText = String(formData.get("yaml_text") ?? "");

  try {
    loadYaml(yamlText);
  } catch (e) {
    const url = new URL("/policy", request.url);
    url.searchParams.set("error", e instanceof Error ? e.message : "invalid YAML");
    return NextResponse.redirect(url, { status: 303 });
  }

  await savePolicyVersion(yamlText);

  const url = new URL("/policy", request.url);
  url.searchParams.set("saved", "1");
  return NextResponse.redirect(url, { status: 303 });
}
