import { getCurrentPolicy, listPolicyVersions } from "@/lib/policy";

export const dynamic = "force-dynamic";

const EXAMPLE_POLICY = `default_action: allow

rules:
  - name: block-deletes
    tool: "delete_*"
    action: block
    reason: "irreversible actions are never auto-allowed"

  - name: approve-large-transfers
    tool: "transfer_funds"
    action: approve
    reason: "transfers over $500 require human approval"
    condition:
      type: arg_exceeds
      arg: amount
      threshold: 500
`;

export default async function PolicyPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; saved?: string }>;
}) {
  const params = await searchParams;
  const current = await getCurrentPolicy();
  const history = await listPolicyVersions(10);

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">Policy</h1>
      <p className="text-neutral-500 text-sm mb-4">
        This is what bastion&apos;s SDK loads via{" "}
        <code className="text-neutral-400">load_policy_from_dashboard()</code>. See{" "}
        <code className="text-neutral-400">examples/policy.yaml</code> in the repo for the
        full rule schema.
      </p>

      {params.error && (
        <p className="text-red-400 text-sm mb-4 font-mono">Invalid YAML: {params.error}</p>
      )}
      {params.saved && <p className="text-green-400 text-sm mb-4">Saved a new policy version.</p>}

      <form method="post" action="/policy/save">
        <textarea
          name="yaml_text"
          defaultValue={current?.yaml_text ?? EXAMPLE_POLICY}
          rows={20}
          spellCheck={false}
          className="w-full bg-neutral-900 border border-neutral-700 rounded px-3 py-2 font-mono text-sm"
        />
        <button
          type="submit"
          className="mt-3 bg-neutral-800 hover:bg-neutral-700 rounded px-4 py-1.5 text-sm"
        >
          Save
        </button>
      </form>

      {history.length > 0 && (
        <div className="mt-10">
          <h2 className="text-sm font-semibold text-neutral-400 mb-3">Version history</h2>
          <ul className="space-y-1 text-sm">
            {history.map((v) => (
              <li key={v.id} className="text-neutral-500">
                {new Date(v.created_at).toLocaleString()}
                {current && v.id === current.id && (
                  <span className="text-neutral-600"> (current)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
