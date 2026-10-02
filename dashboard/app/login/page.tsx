export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const params = await searchParams;

  return (
    <div className="max-w-sm mx-auto mt-24">
      <h1 className="text-xl font-semibold mb-4">Sign in</h1>
      {params.error && <p className="text-red-400 text-sm mb-4">Incorrect password.</p>}
      <form method="post" action="/api/auth/login" className="space-y-3">
        <input type="hidden" name="next" value={params.next ?? "/audit"} />
        <input
          type="password"
          name="password"
          placeholder="Password"
          autoFocus
          required
          className="w-full bg-neutral-900 border border-neutral-700 rounded px-3 py-2"
        />
        <button
          type="submit"
          className="w-full bg-neutral-800 hover:bg-neutral-700 rounded px-4 py-2"
        >
          Sign in
        </button>
      </form>
    </div>
  );
}
