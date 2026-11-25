"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DataTable, LineChart, StatTile } from "@/components/charts";
import { type EvalLearner, type EvalRun, type Progress, fetchEval, fetchProgress } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

/** How we know it works: simulated learners with planted weaknesses, scored against ground truth. */
export default function EvalPage() {
  const [runs, setRuns] = useState<Record<string, EvalRun> | null>(null);
  const [tag, setTag] = useState<string>("main");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEval().then(
      (r) => {
        setRuns(r);
        setTag((t) => (r[t] ? t : (Object.keys(r)[0] ?? t)));
      },
      (e) => setError(String(e)),
    );
  }, []);

  const run = runs?.[tag];
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Does it work? Simulated learners</h1>
          <p className="text-xs text-[var(--muted)]">
            LLM learners speak correct English; rules plant known errors at known rates, so every
            detection can be scored. Learning is simulated: a targeted skill&apos;s error rate drops
            25% per session, others 3%.
          </p>
        </div>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm [&>a]:whitespace-nowrap">
          {runs && (
            <select
              aria-label="Run" value={tag} onChange={(e) => setTag(e.target.value)}
              className="rounded-lg bg-[var(--surface)] px-2 py-1"
            >
              {Object.entries(runs).map(([k, r]) => (
                <option key={k} value={k}>
                  {k} ({r.planner} planner)
                </option>
              ))}
            </select>
          )}
          <Link href="/progress" className="text-[var(--muted)] hover:text-[var(--fg)]">
            Growth
          </Link>
        </nav>
      </header>
      {error && <p className="text-[var(--danger)]">{error}</p>}
      {runs && !run && <p className="text-[var(--muted)]">No simulation results yet. Run `make sim`.</p>}
      {runs?.main && runs?.control && <ABCompare main={runs.main} control={runs.control} />}
      {run &&
        Object.entries(run.learners).map(([uid, L]) => (
          <LearnerCard key={uid} uid={uid} L={L} sessions={run.sessions} />
        ))}
    </main>
  );
}

function finalPlantedRate(L: EvalLearner, chats?: number) {
  const last = (chats ? L.true_rates[chats - 1] : L.true_rates.at(-1)) ?? {};
  const ks = Object.keys(L.planted);
  return ks.reduce((a, k) => a + (last[k] ?? 0), 0) / ks.length;
}

function ABCompare({ main, control }: { main: EvalRun; control: EvalRun }) {
  const pairs = Object.entries(control.learners)
    .map(([cid, c]) => {
      const mid = Object.keys(main.learners).find((m) => cid.startsWith(m));
      if (!mid || !c.true_rates.length) return null;
      // Compare at equal chat counts: a control run cut short by provider quotas is still fair.
      const chats = Math.min(main.learners[mid].true_rates.length, c.true_rates.length);
      return { name: c.name, tutor: main.learners[mid], ctrl: c, chats };
    })
    .filter((p): p is NonNullable<typeof p> => p != null);
  if (!pairs.length) return null;
  return (
    <section className="rounded-2xl bg-[var(--surface)] p-4">
      <h2 className="mb-1 text-sm font-medium">Tutor planner vs random targets</h2>
      <p className="mb-3 text-xs text-[var(--muted)]">
        Same learner, same seed, compared after the same number of chats. Only what the Friend
        steers toward differs.
      </p>
      {pairs.map((p) => {
        const start = Object.values(p.tutor.planted).reduce((a, b) => a + b, 0) / Object.keys(p.tutor.planted).length;
        return (
          <div key={p.name} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label={`${p.name}: planted error rate at start`} value={pct(start)} />
            <StatTile label={`After ${p.chats - 1} chats, tutor planner`} value={pct(finalPlantedRate(p.tutor, p.chats))} />
            <StatTile label={`After ${p.chats - 1} chats, random targets`} value={pct(finalPlantedRate(p.ctrl, p.chats))} />
            <StatTile
              label="Chats that targeted a real weakness"
              value={pct(p.tutor.score.planner.sessions_targeting_a_planted_skill)}
              hint={`random: ${pct(p.ctrl.score.planner.sessions_targeting_a_planted_skill)}`}
            />
          </div>
        );
      })}
    </section>
  );
}

function LearnerCard({ uid, L, sessions }: { uid: string; L: EvalLearner; sessions: number }) {
  const [prog, setProg] = useState<Progress | null>(null);
  const [table, setTable] = useState(false);
  useEffect(() => {
    fetchProgress(uid).then(setProg, () => setProg(null));
  }, [uid]);

  const xs = Array.from({ length: L.true_rates.length }, (_, i) => `#${i + 1}`);
  const planted = Object.keys(L.planted);
  const measured = useMemo(() => {
    const out: Record<string, (number | null)[]> = {};
    if (!prog) return out;
    const idx = prog.sessions.map((s, i) => (s.metrics ? i : -1)).filter((i) => i >= 0);
    for (const k of planted) {
      const h = prog.skill_history[k];
      out[k] = idx.map((i) => (h?.[i] == null ? null : 1 - (h[i] as number)));
    }
    return out;
  }, [prog, planted]);
  const s = L.score;

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-[var(--viz-grid)] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-medium">
          {L.name} <span className="text-sm text-[var(--muted)]">· {L.level} · {L.l1} speaker · {sessions} chats</span>
        </h2>
        <Link href={`/progress?user=${encodeURIComponent(uid)}`} className="text-xs text-[var(--muted)] underline">
          Open their growth page
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatTile label="Analyst precision" value={pct(s.analyst.overall.precision)} hint={`${s.analyst.overall.tp} hits, ${s.analyst.overall.fp} false alarms`} />
        <StatTile label="Analyst recall" value={pct(s.analyst.overall.recall)} hint={`${s.analyst.overall.fn} planted errors missed`} />
        <StatTile label="Chats targeting a real weakness" value={pct(s.planner.sessions_targeting_a_planted_skill)} />
        <StatTile label="Friend sounded like a teacher" value={pct(s.friend.teacher_leak_rate)} hint={`of ${s.friend.replies} replies`} />
        <StatTile
          label="Correct form echoed back"
          value={pct(s.friend.recast_rate)}
          hint={s.friend.modeled_within_2_rate != null ? `within 2 replies: ${pct(s.friend.modeled_within_2_rate)}` : undefined}
        />
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Planted weakness: true vs measured error rate</h3>
          <p className="text-xs text-[var(--muted)]">
            True = the simulator&apos;s planted rate (dashed). Measured = 1 − the Tutor&apos;s mastery estimate.
          </p>
        </div>
        <button onClick={() => setTable(!table)} className="text-xs text-[var(--muted)] underline">
          {table ? "Show charts" : "Show table"}
        </button>
      </div>
      {table ? (
        <DataTable
          columns={["Chat", ...planted.flatMap((k) => [`${k} true`, `${k} measured`]), "Targets"]}
          rows={xs.map((x, i) => [
            x,
            ...planted.flatMap((k) => [pct(L.true_rates[i]?.[k]), pct(measured[k]?.[i])]),
            L.targets[i]?.join(", ") ?? "",
          ])}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {planted.map((k) => (
            <LineChart
              key={k}
              title={k.replaceAll("_", " ")}
              subtitle={`targeted in chats ${L.targets.map((t, i) => (t.includes(k) ? `#${i + 1}` : null)).filter(Boolean).join(", ") || "none"}`}
              xLabels={xs}
              yDomain={[0, 1]}
              yFormat={(v) => `${Math.round(v * 100)}%`}
              height={170}
              dashed={["true"]}
              series={[
                { id: "true", label: "True rate", values: L.true_rates.map((r) => r[k] ?? null) },
                { id: "measured", label: "Measured", values: measured[k] ?? [] },
              ]}
            />
          ))}
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-[var(--muted)]">Analyst precision and recall per skill</summary>
        <div className="mt-2">
          <DataTable
            columns={["Skill", "Planted?", "Hits", "False alarms", "Missed", "Precision", "Recall"]}
            rows={Object.entries(s.analyst.per_skill).map(([k, v]) => [
              k, planted.includes(k) ? "yes" : "", v.tp, v.fp, v.fn, pct(v.precision), pct(v.recall),
            ])}
          />
        </div>
      </details>
      {s.friend.leaks.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-[var(--muted)]">Replies where the Friend sounded like a teacher</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {s.friend.leaks.map((l, i) => (
              <li key={i}>
                “{l.reply}” <span className="text-[var(--muted)]">(matched “{l.match}”)</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
