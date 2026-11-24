"use client";

import {
  BarVisualizer,
  DisconnectButton,
  RoomAudioRenderer,
  StartAudio,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { useEffect, useRef } from "react";

const STATE_LABEL: Record<string, string> = {
  disconnected: "Calling…",
  connecting: "Calling…",
  initializing: "Maya is picking up…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Maya is talking",
};

/** In-call UI. Deliberately looks like a phone call with a friend, not a lesson:
 * no scores, no corrections, just captions you can glance at. */
export function CallView() {
  const { state, audioTrack, agent } = useVoiceAssistant();
  const transcripts = useTranscriptions();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts.length]);

  return (
    <div className="flex w-full max-w-xl flex-1 flex-col items-center gap-6">
      <div className="flex h-40 w-full items-center justify-center">
        <BarVisualizer
          state={state}
          track={audioTrack}
          barCount={5}
          className="voisai-visualizer h-32 w-64"
        />
      </div>
      <p className="text-sm text-[var(--muted)]">{STATE_LABEL[state] ?? state}</p>

      <div className="flex max-h-[40vh] w-full flex-col gap-2 overflow-y-auto rounded-2xl bg-[var(--surface)] p-4 text-[15px] leading-relaxed">
        {transcripts.length === 0 && (
          <p className="text-center text-[var(--muted)]">Say hi whenever you&apos;re ready.</p>
        )}
        {transcripts.map((t) => {
          const fromAgent = t.participantInfo.identity === agent?.identity;
          return (
            <p
              key={t.streamInfo.id}
              className={fromAgent ? "text-[var(--fg)]" : "self-end text-right text-[var(--accent)]"}
            >
              {t.text}
            </p>
          );
        })}
        <div ref={endRef} />
      </div>

      <DisconnectButton className="rounded-full bg-[var(--danger)] px-8 py-3 font-medium text-white">
        End call
      </DisconnectButton>
      <RoomAudioRenderer />
      <StartAudio label="Tap to enable audio" className="rounded-full bg-[var(--accent)] px-6 py-2 text-white" />
    </div>
  );
}
