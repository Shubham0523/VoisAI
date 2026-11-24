"use client";

import { LiveKitRoom } from "@livekit/components-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CallView } from "@/components/CallView";
import { type Connection, fetchConnection, wakeApi } from "@/lib/api";

export default function Home() {
  const [conn, setConn] = useState<Connection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [awake, setAwake] = useState(false);

  useEffect(() => {
    const ctl = new AbortController();
    wakeApi(ctl.signal).then(
      () => setAwake(true),
      () => !ctl.signal.aborted && setAwake(true), // let the click surface the real error
    );
    return () => ctl.abort();
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setConn(await fetchConnection());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <main className="flex min-h-dvh flex-col items-center px-4 py-8">
      <header className="mb-8 flex w-full max-w-xl items-center justify-between">
        <h1 className="text-lg font-semibold">VoisAI</h1>
        <Link href="/progress" className="text-sm text-[var(--muted)] hover:text-[var(--fg)]">
          Your growth
        </Link>
      </header>

      {conn ? (
        <LiveKitRoom
          serverUrl={conn.serverUrl}
          token={conn.token}
          connect
          audio
          video={false}
          onDisconnected={() => setConn(null)}
          onError={(e) => setError(e.message)}
          className="flex w-full flex-1 flex-col items-center"
        >
          <CallView />
        </LiveKitRoom>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
          <div className="h-28 w-28 rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-2)] shadow-lg" />
          <div>
            <h2 className="text-2xl font-semibold">Call Maya</h2>
            <p className="mt-2 max-w-sm text-[var(--muted)]">
              Talk about your day, your plans, anything at all.
            </p>
          </div>
          <button
            onClick={start}
            disabled={busy}
            className="rounded-full bg-[var(--accent)] px-10 py-3 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Connecting…" : "Start talking"}
          </button>
          {!awake && (
            <p className="text-xs text-[var(--muted)]">Waking up the server, this can take a minute…</p>
          )}
          {error && <p className="max-w-sm text-sm text-[var(--danger)]">{error}</p>}
        </div>
      )}
    </main>
  );
}
