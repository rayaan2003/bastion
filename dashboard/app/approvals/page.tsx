import { revalidatePath } from "next/cache";
import { decideApproval, listApprovals } from "@/lib/approvals";

// This page reads live DB state on every request (the pending approval
// queue) - it must never be statically prerendered at build time.
export const dynamic = "force-dynamic";

async function approve(formData: FormData) {
  "use server";
  const id = formData.get("id") as string;
  await decideApproval(id, "approved");
  revalidatePath("/approvals");
}

async function deny(formData: FormData) {
  "use server";
  const id = formData.get("id") as string;
  await decideApproval(id, "denied");
  revalidatePath("/approvals");
}

export default async function ApprovalsPage() {
  const pending = await listApprovals("pending");

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Pending Approvals</h1>

      {pending.length === 0 ? (
        <p className="text-neutral-500 text-sm">No pending approvals right now.</p>
      ) : (
        <ul className="space-y-4">
          {pending.map((req) => (
            <li
              key={req.id}
              className="border border-neutral-800 rounded-lg p-4 flex justify-between items-start gap-4"
            >
              <div>
                <p className="font-mono text-sm mb-1">{req.tool_name}</p>
                <p className="text-neutral-400 text-sm mb-1">{req.reason}</p>
                <p className="text-neutral-500 text-xs font-mono">{JSON.stringify(req.args)}</p>
                <p className="text-neutral-600 text-xs mt-1">
                  {new Date(req.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <form action={approve}>
                  <input type="hidden" name="id" value={req.id} />
                  <button
                    type="submit"
                    className="bg-green-900 hover:bg-green-800 text-green-100 rounded px-3 py-1.5 text-sm"
                  >
                    Approve
                  </button>
                </form>
                <form action={deny}>
                  <input type="hidden" name="id" value={req.id} />
                  <button
                    type="submit"
                    className="bg-red-900 hover:bg-red-800 text-red-100 rounded px-3 py-1.5 text-sm"
                  >
                    Deny
                  </button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
