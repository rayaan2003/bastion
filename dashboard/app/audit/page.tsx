import { listEvents } from "@/lib/events";

// Reads live DB state and query-string filters on every request - never
// statically prerender this page.
export const dynamic = "force-dynamic";

const ACTION_COLORS: Record<string, string> = {
  allowed: "text-green-400",
  approved: "text-green-400",
  blocked: "text-red-400",
  denied: "text-red-400",
};

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ tool_name?: string; action?: string; session_id?: string }>;
}) {
  const params = await searchParams;
  const events = await listEvents({
    toolName: params.tool_name || undefined,
    action: params.action || undefined,
    sessionId: params.session_id || undefined,
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
        </select>
        <input
          name="session_id"
          defaultValue={params.session_id ?? ""}
          placeholder="session id"
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
                </td>
                <td className="py-2 pr-4 text-neutral-400 max-w-xs truncate">{event.reason}</td>
                <td className="py-2 pr-4 text-neutral-500 max-w-xs truncate font-mono text-xs">
                  {JSON.stringify(event.args)}
                </td>
                <td className="py-2 pr-4 text-neutral-500 font-mono text-xs">
                  {event.session_id.slice(0, 8)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
