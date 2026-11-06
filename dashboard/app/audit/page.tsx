import { listEvents } from "@/lib/events";

// Reads live DB state and query-string filters on every request - never
// statically prerender this page.
export const dynamic = "force-dynamic";

const ACTION_COLORS: Record<string, string> = {
  allowed: "text-green-400",
  approved: "text-green-400",
  blocked: "text-red-400",
  denied: "text-red-400",
  would_block: "text-amber-400",
  would_approve: "text-amber-400",
  would_allow: "text-amber-400",
  completed: "text-neutral-400",
  failed: "text-orange-400",
};

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{
    tool_name?: string;
    action?: string;
    session_id?: string;
    call_id?: string;
  }>;
}) {
  const params = await searchParams;
  const events = await listEvents({
    toolName: params.tool_name || undefined,
    action: params.action || undefined,
    sessionId: params.session_id || undefined,
    callId: params.call_id || undefined,
  });

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Audit Log</h1>

      <form className="flex gap-3 mb-6 text-sm" method="get">
        <input
          name="tool_name"
          defaultValue={params.tool_name ?? ""}
          placeholder="tool name"
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-1.5"
        />
        <select
          name="action"
          defaultValue={params.action ?? ""}
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-1.5"
        >
          <option value="">any action</option>
          <option value="allowed">allowed</option>
          <option value="blocked">blocked</option>
          <option value="approved">approved</option>
          <option value="denied">denied</option>
          <option value="would_block">would_block (shadow)</option>
          <option value="would_approve">would_approve (shadow)</option>
          <option value="would_allow">would_allow (shadow)</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
        <input
          name="session_id"
          defaultValue={params.session_id ?? ""}
          placeholder="session id"
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-1.5"
        />
        <input
          name="call_id"
          defaultValue={params.call_id ?? ""}
          placeholder="call id"
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-1.5"
        />
        <button
          type="submit"
          className="bg-neutral-800 hover:bg-neutral-700 rounded px-4 py-1.5"
        >
          Filter
        </button>
      </form>

      {events.length === 0 ? (
        <p className="text-neutral-500 text-sm">No events match these filters.</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-800">
              <th className="py-2 pr-4">Time</th>
              <th className="py-2 pr-4">Tool</th>
              <th className="py-2 pr-4">Action</th>
              <th className="py-2 pr-4">Reason</th>
              <th className="py-2 pr-4">Args</th>
              <th className="py-2 pr-4">Session</th>
              <th className="py-2 pr-4">Call</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id} className="border-b border-neutral-900">
                <td className="py-2 pr-4 whitespace-nowrap text-neutral-400">
                  {new Date(event.timestamp * 1000).toLocaleString()}
                </td>
                <td className="py-2 pr-4 font-mono">{event.tool_name}</td>
                <td className={`py-2 pr-4 font-medium ${ACTION_COLORS[event.action] ?? ""}`}>
                  {event.action}
                  {event.approver ? (
                    <span className="block text-xs font-normal text-neutral-500">
                      by {event.approver}
                    </span>
                  ) : null}
                </td>
                <td className="py-2 pr-4 text-neutral-400 max-w-xs truncate">{event.reason}</td>
                <td className="py-2 pr-4 text-neutral-500 max-w-xs truncate font-mono text-xs">
                  {JSON.stringify(event.args)}
                </td>
                <td className="py-2 pr-4 text-neutral-500 font-mono text-xs">
                  {event.session_id.slice(0, 8)}
                </td>
                <td className="py-2 pr-4 font-mono text-xs">
                  {event.call_id ? (
                    <a
                      href={`/audit?call_id=${encodeURIComponent(event.call_id)}`}
                      className="text-neutral-500 hover:text-neutral-300 underline"
                      title="All events for this call"
                    >
                      {event.call_id.slice(0, 8)}
                    </a>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
