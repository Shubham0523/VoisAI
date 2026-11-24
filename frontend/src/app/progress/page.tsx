"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { DataTable, LineChart, MasteryBars, StatTile } from "@/components/charts";
import { type Progress, type UserRow, fetchProgress, fetchUsers, getUserId } from "@/lib/api";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Optional growth view. The call screen never shows any of this; the learner chooses to look. */
export default function ProgressPage() {
  return (
    <Suspense fallback={<main className="p-8 text-[var(--muted)]">Loading…</main>}>
      <Growth />
    </Suspense>
  );
}

function Growth() {
  const params = useSearchParams();
  const router = useRouter();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [table, setTable] = useState(false);
  const userId = params.get("user") ?? getUserId();

  useEffect(() => {
    fetchUsers().then(setUsers, () => setUsers([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = userId
      ? fetchProgress(userId)
      : Promise.reject(new Error("Have your first chat with Maya, then come back here."));
    load.then(
      (d) => !cancelled && (setData(d), setError(null)),
      (e) => !cancelled && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [userId]);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Your growth</h1>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm [&>a]:whitespace-nowrap">
          {users.length > 0 && (
            <select
              aria-label="Learner"
              value={userId ?? ""}
              onChange={(e) => router.push(`/progress?user=${encodeURIComponent(e.target.value)}`)}
              className="max-w-[12rem] rounded-lg bg-[var(--surface)] px-2 py-1 text-sm"
            >
              {!userId && <option value="">Choose a learner</option>}
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} {u.is_simulated ? "(simulated)" : ""} · {u.sessions} chats
                </option>
              ))}
            </select>
          )}
          <Link href="/eval" className="text-[var(--muted)] hover:text-[var(--fg)]">
            Evaluation
          </Link>
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--fg)]">
            Back to Maya
          </Link>
        </nav>
      </header>
      {error && <p className="text-[var(--muted)]">{error}</p>}
      {data && <Dashboard data={data} table={table} setTable={setTable} />}
    </main>
  );
}

function Dashboard({ data, table, setTable }: { data: Progress; table: boolean; setTable: (v: boolean) => void }) {
  const done = data.sessions.filter((s) => s.metrics);
  const xs = done.map((s) => `#${s.n}`);
  const first = done[0]?.metrics;
  const last = done.at(-1)?.metrics;
  const usedWords = data.vocab.filter((v) => v.status === "used");
  const latestRecap = [...data.sessions].reverse().find((s) => s.recap)?.recap;

  const skillName = useMemo(
    () => Object.fromEntries(data.skills.map((s) => [s.skill_id, s.name])),
    [data.skills],
  );
  // Plot the 4 skills with the most evidence: they're the ones the story is about.
  const tracked = [...data.skills].sort((a, b) => b.evidence - a.evidence).slice(0, 4);
  const sessionIdx = data.sessions.map((s, i) => (s.metrics ? i : -1)).filter((i) => i >= 0);

  if (!done.length) return <p className="text-[var(--muted)]">Still getting to know you. Keep chatting.</p>;

  const delta = (a: number | null | undefined, b: number | null | undefined, lowerBetter: boolean, fmt: (v: number) => string) => {
    if (a == null || b == null || done.length < 2) return undefined;
    const better = lowerBetter ? b < a : b > a;
    return `${better ? "▲ better" : b === a ? "no change" : "▼ worse"} than chat #1 (${fmt(a)})`;
  };

  return (
    <>
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Level estimate" value={data.user.level ?? "–"} hint={data.user.level ? "CEFR, heuristic" : "needs more chats"} />
        <StatTile label="Chats" value={String(data.sessions.length)} />
        <StatTile
          label="Errors per 100 words"
          value={last?.errors_per_100w?.toFixed(1) ?? "–"}
          delta={delta(first?.errors_per_100w, last?.errors_per_100w, true, (v) => v.toFixed(1))}
        />
        <StatTile label="New words you used" value={String(usedWords.length)} hint={`${data.vocab.length} heard`} />
      </section>

      {latestRecap && (
        <section className="rounded-2xl bg-[var(--surface)] p-4 text-sm">
          <div className="mb-2 text-xs text-[var(--muted)]">From your last chat</div>
          <div className="flex flex-col gap-2">
            {latestRecap.polish && (
              <p>
                You said <span className="italic">“{latestRecap.polish.you_said}”</span>. People often say{" "}
                <span className="font-medium">“{latestRecap.polish.natural}”</span>.
              </p>
            )}
            {latestRecap.win && (
              <p>
                Nice: you got <span className="font-medium">{latestRecap.win.skill.toLowerCase()}</span> right{" "}
                {latestRecap.win.times}× in a row.
              </p>
            )}
            {latestRecap.word && (
              <p>
                Word of the day: <span className="font-medium">{latestRecap.word.word}</span> ({latestRecap.word.meaning})
                {latestRecap.word.you_used_it ? ". You used it yourself!" : "."}
              </p>
            )}
          </div>
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-3">
        <LineChart
          title="Errors per 100 words" subtitle="lower is better" xLabels={xs} height={170}
          series={[{ id: "e", label: "Errors / 100 words", values: done.map((s) => s.metrics!.errors_per_100w) }]}
          yFormat={(v) => v.toFixed(1)}
        />
        <LineChart
          title="Vocabulary range" subtitle="MATTR, higher is richer" xLabels={xs} height={170}
          series={[{ id: "m", label: "MATTR", values: done.map((s) => s.metrics!.mattr) }]}
          yFormat={(v) => v.toFixed(2)}
        />
        <LineChart
          title="Focus-skill accuracy" subtitle="skills the chat quietly practised" xLabels={xs} height={170}
          series={[{ id: "t", label: "Accuracy", values: done.map((s) => s.metrics!.target_accuracy) }]}
          yDomain={[0, 1]} yFormat={pct}
        />
      </section>

      {tracked.length > 0 && (
        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">Skills over time</h2>
            <button onClick={() => setTable(!table)} className="text-xs text-[var(--muted)] underline">
              {table ? "Show chart" : "Show table"}
            </button>
          </div>
          {table ? (
            <DataTable
              columns={["Chat", ...tracked.map((t) => t.name)]}
              rows={sessionIdx.map((i, k) => [
                xs[k],
                ...tracked.map((t) => {
                  const v = data.skill_history[t.skill_id]?.[i];
                  return v == null ? null : pct(v);
                }),
              ])}
            />
          ) : (
            <LineChart
              title="Estimated mastery" subtitle="chance of getting it right when it's needed"
              xLabels={xs} yDomain={[0, 1]} yFormat={pct} height={220}
              series={tracked.map((t) => ({
                id: t.skill_id,
                label: skillName[t.skill_id] ?? t.skill_id,
                values: sessionIdx.map((i) => data.skill_history[t.skill_id]?.[i] ?? null),
              }))}
            />
          )}
        </section>
      )}

      <MasteryBars
        title="Where you are now"
        subtitle="bar = estimate, line = likely range; a wide line means not enough evidence yet"
        bars={data.skills.map((s) => ({
          id: s.skill_id, label: s.name, value: s.mastery, low: s.low, high: s.high,
          note: `${s.status}, ${s.evidence} observations`,
        }))}
      />

      {data.vocab.length > 0 && (
        <section className="rounded-2xl bg-[var(--card)] p-4">
          <div className="mb-2 text-sm font-medium">Words from your chats</div>
          <ul className="flex flex-wrap gap-2 text-xs">
            {data.vocab.map((v) => (
              <li
                key={v.word}
                title={v.meaning ?? ""}
                className={`rounded-full px-3 py-1 ${v.status === "used" ? "bg-[var(--series-1)] text-white" : "bg-[var(--surface)] text-[var(--ink-2)]"}`}
              >
                {v.word}
                {v.status === "used" ? " ✓" : ""}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-[var(--muted)]">✓ = you used it yourself, without Maya saying it first</p>
        </section>
      )}

      {data.benchmarks.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">Then vs now: “tell me about a trip you loved”</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.benchmarks.map((b) => (
              <div key={b.session} className="rounded-2xl bg-[var(--card)] p-4 text-sm">
                <div className="mb-2 text-xs text-[var(--muted)]">
                  Chat #{b.session}
                  {b.metrics?.errors_per_100w != null && ` · ${b.metrics.errors_per_100w.toFixed(1)} errors/100w`}
                  {b.metrics?.mattr != null && ` · range ${b.metrics.mattr.toFixed(2)}`}
                </div>
                <p className="leading-relaxed">“{b.text}”</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
