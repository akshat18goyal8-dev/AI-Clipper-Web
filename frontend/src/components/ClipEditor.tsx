"use client";

import React, { useEffect, useState } from "react";
import { API_BASE, ClipItem, EditTimeline, apiFetch, getToken } from "@/lib/api";
import { RotateCcw, RotateCw, Save, Download, Sparkles, Plus, Trash2 } from "lucide-react";

interface ClipEditorProps {
  clip: ClipItem | null;
  presets: string[];
  intensities: string[];
  musicTracks: string[];
  onRefresh: () => void;
}

export default function ClipEditor({
  clip,
  presets,
  intensities,
  musicTracks,
  onRefresh,
}: ClipEditorProps) {
  const [timeline, setTimeline] = useState<EditTimeline | null>(null);
  const [undoStack, setUndoStack] = useState<EditTimeline[]>([]);
  const [redoStack, setRedoStack] = useState<EditTimeline[]>([]);
  const [rendering, setRendering] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [videoBust, setVideoBust] = useState(Date.now());
  const [tab, setTab] = useState<"captions" | "effects" | "audio" | "score">("captions");

  useEffect(() => {
    if (clip) {
      setTimeline(JSON.parse(JSON.stringify(clip.timeline)));
      setUndoStack([]);
      setRedoStack([]);
      setStatusMsg("");
      setVideoBust(Date.now());
    }
  }, [clip?.clip_id]);

  if (!clip || !timeline) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-[#0E1525] p-10 text-center text-slate-400">
        Select a clip from <span className="font-semibold text-cyan-400">My Clips</span> to inspect, trim, edit dynamic captions, mix audio, and re-render.
      </div>
    );
  }

  const updateTl = (updater: (draft: EditTimeline) => EditTimeline) => {
    setUndoStack((prev) => [...prev, JSON.parse(JSON.stringify(timeline))]);
    setRedoStack([]);
    setTimeline(updater(JSON.parse(JSON.stringify(timeline))));
  };

  const undo = () => {
    if (!undoStack.length) return;
    const prev = undoStack[undoStack.length - 1];
    setRedoStack((r) => [...r, JSON.parse(JSON.stringify(timeline))]);
    setUndoStack((u) => u.slice(0, -1));
    setTimeline(prev);
  };

  const redo = () => {
    if (!redoStack.length) return;
    const next = redoStack[redoStack.length - 1];
    setUndoStack((u) => [...u, JSON.parse(JSON.stringify(timeline))]);
    setRedoStack((r) => r.slice(0, -1));
    setTimeline(next);
  };

  const handleSaveAndRender = async () => {
    setRendering(true);
    setStatusMsg("Saving timeline and re-rendering 1080×1920 vertical clip...");
    try {
      await apiFetch(`/api/clips/${clip.clip_id}/timeline`, {
        method: "PUT",
        body: JSON.stringify(timeline),
      });
      await apiFetch(`/api/clips/${clip.clip_id}/render`, { method: "POST" });
      setVideoBust(Date.now());
      setStatusMsg("Re-rendered successfully!");
      onRefresh();
    } catch (e: unknown) {
      setStatusMsg(`Render failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setRendering(false);
    }
  };

  const token = getToken() || "";
  const videoSrc = `${API_BASE}/api/clips/${clip.clip_id}/video?token=${encodeURIComponent(token)}&v=${videoBust}`;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white">Clip Editor — {clip.title}</h2>
          <p className="text-sm text-slate-400">
            Score: <span className="font-semibold text-emerald-400">{clip.score.toFixed(1)}/100</span> • Duration:{" "}
            {(timeline.trim_end - timeline.trim_start).toFixed(1)}s • 1080×1920 Vertical
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={undo}
            disabled={!undoStack.length}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-40"
          >
            <RotateCcw className="h-4 w-4" /> Undo
          </button>
          <button
            onClick={redo}
            disabled={!redoStack.length}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-40"
          >
            <RotateCw className="h-4 w-4" /> Redo
          </button>
          <button
            onClick={handleSaveAndRender}
            disabled={rendering}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-2 text-xs font-bold text-white shadow hover:opacity-95 disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" /> {rendering ? "Rendering..." : "Apply & Preview Render"}
          </button>
          <a
            href={videoSrc}
            download={`${clip.clip_id}.mp4`}
            className="flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-xs font-bold text-cyan-300 hover:bg-cyan-500/20"
          >
            <Download className="h-4 w-4" /> Download MP4
          </a>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/30 px-4 py-2.5 text-sm text-cyan-200">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left: Video Preview + Timeline Trim & Reframe */}
        <div className="space-y-4 lg:col-span-5">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-black p-2">
            <video
              key={videoSrc}
              src={videoSrc}
              controls
              className="mx-auto aspect-[9/16] max-h-[460px] w-full rounded-xl bg-black object-contain"
            />
          </div>

          <div className="space-y-3 rounded-2xl border border-slate-800 bg-[#0E1525] p-4">
            <h3 className="text-sm font-bold text-cyan-400">Timeline Trim & Reframe</h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-slate-400">
                Trim Start (s)
                <input
                  type="number"
                  step="0.5"
                  min={0}
                  value={timeline.trim_start}
                  onChange={(e) => updateTl((d) => ({ ...d, trim_start: Math.max(0, Number(e.target.value)) }))}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-1.5 text-sm text-white"
                />
              </label>
              <label className="text-xs text-slate-400">
                Trim End (s)
                <input
                  type="number"
                  step="0.5"
                  min={1}
                  value={timeline.trim_end}
                  onChange={(e) =>
                    updateTl((d) => ({
                      ...d,
                      trim_end: Math.min(d.trim_start + 60, Math.max(d.trim_start + 1.5, Number(e.target.value))),
                    }))
                  }
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-1.5 text-sm text-white"
                />
              </label>
            </div>

            <div className="flex flex-wrap gap-2">
              {[10, 15, 30, 45, 60].map((sec) => (
                <button
                  key={sec}
                  onClick={() => updateTl((d) => ({ ...d, trim_end: Number((d.trim_start + sec).toFixed(2)) }))}
                  className="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-semibold text-slate-200 hover:border-cyan-400"
                >
                  {sec}s
                </button>
              ))}
              <button
                onClick={() =>
                  updateTl((d) => ({
                    ...d,
                    trim_end: Number(((d.trim_start + d.trim_end) * 0.5).toFixed(2)),
                  }))
                }
                className="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:border-amber-400"
              >
                Split Half
              </button>
            </div>

            <label className="block text-xs text-slate-400">
              Reframe Mode
              <select
                value={timeline.reframe_mode}
                onChange={(e) => updateTl((d) => ({ ...d, reframe_mode: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
              >
                <option value="smart_track">Smart Subject Tracking (9:16)</option>
                <option value="blur_fill">Blurred Ambient Fill (Full Frame)</option>
                <option value="split_gaming">Gaming Split Focus</option>
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-slate-400">
                Crop Pan X ({Math.round(timeline.crop_offset_x * 100)}%)
                <input
                  type="range"
                  min={-100}
                  max={100}
                  value={Math.round(timeline.crop_offset_x * 100)}
                  onChange={(e) => updateTl((d) => ({ ...d, crop_offset_x: Number(e.target.value) / 100 }))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <label className="text-xs text-slate-400">
                Crop Pan Y ({Math.round(timeline.crop_offset_y * 100)}%)
                <input
                  type="range"
                  min={-100}
                  max={100}
                  value={Math.round(timeline.crop_offset_y * 100)}
                  onChange={(e) => updateTl((d) => ({ ...d, crop_offset_y: Number(e.target.value) / 100 }))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
            </div>
          </div>
        </div>

        {/* Right: Tabbed Inspector */}
        <div className="rounded-2xl border border-slate-800 bg-[#0E1525] p-5 lg:col-span-7">
          <div className="mb-4 flex flex-wrap gap-2 border-b border-slate-800 pb-3">
            {(
              [
                ["captions", "Captions & Style"],
                ["effects", "Hook, Preset & Intro/Outro"],
                ["audio", "Audio & Music"],
                ["score", "AI Engagement Score"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`rounded-lg px-3.5 py-2 text-xs font-bold transition ${
                  tab === id ? "bg-blue-600 text-white" : "bg-slate-900 text-slate-400 hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "captions" && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <label className="text-xs text-slate-400">
                  Font Size
                  <input
                    type="number"
                    min={36}
                    max={120}
                    value={timeline.caption_style.font_size}
                    onChange={(e) =>
                      updateTl((d) => ({
                        ...d,
                        caption_style: { ...d.caption_style, font_size: Number(e.target.value) },
                      }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-2.5 py-1.5 text-sm text-white"
                  />
                </label>
                <label className="text-xs text-slate-400">
                  Animation
                  <select
                    value={timeline.caption_style.animation}
                    onChange={(e) =>
                      updateTl((d) => ({
                        ...d,
                        caption_style: { ...d.caption_style, animation: e.target.value },
                      }))
                    }
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-2.5 py-1.5 text-sm text-white"
                  >
                    {["pop", "bounce", "slide", "fade"].map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-slate-400">
                  Highlight Color
                  <input
                    type="color"
                    value={timeline.caption_style.highlight_color}
                    onChange={(e) =>
                      updateTl((d) => ({
                        ...d,
                        caption_style: { ...d.caption_style, highlight_color: e.target.value },
                      }))
                    }
                    className="mt-1 h-9 w-full cursor-pointer rounded-lg border border-slate-700 bg-[#070B14] p-1"
                  />
                </label>
                <label className="flex items-center gap-2 pt-5 text-xs font-semibold text-slate-200">
                  <input
                    type="checkbox"
                    checked={timeline.caption_style.uppercase}
                    onChange={(e) =>
                      updateTl((d) => ({
                        ...d,
                        caption_style: { ...d.caption_style, uppercase: e.target.checked },
                      }))
                    }
                    className="accent-cyan-400"
                  />
                  Uppercase
                </label>
              </div>

              <div className="max-h-[340px] space-y-2 overflow-y-auto pr-1">
                {timeline.captions.map((cue, idx) => (
                  <div key={cue.id + idx} className="grid grid-cols-12 items-center gap-2 rounded-lg border border-slate-800 bg-[#070B14] p-2">
                    <input
                      type="number"
                      step="0.1"
                      value={cue.start}
                      onChange={(e) =>
                        updateTl((d) => {
                          d.captions[idx].start = Number(e.target.value);
                          return d;
                        })
                      }
                      className="col-span-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white"
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={cue.end}
                      onChange={(e) =>
                        updateTl((d) => {
                          d.captions[idx].end = Number(e.target.value);
                          return d;
                        })
                      }
                      className="col-span-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white"
                    />
                    <input
                      type="text"
                      value={cue.text}
                      onChange={(e) =>
                        updateTl((d) => {
                          d.captions[idx].text = e.target.value;
                          return d;
                        })
                      }
                      className="col-span-7 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white"
                    />
                    <button
                      onClick={() =>
                        updateTl((d) => {
                          d.captions.splice(idx, 1);
                          return d;
                        })
                      }
                      className="col-span-1 flex justify-center text-rose-400 hover:text-rose-300"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>

              <button
                onClick={() =>
                  updateTl((d) => {
                    d.captions.push({
                      id: `cue_${Date.now()}`,
                      start: 0,
                      end: 2,
                      text: "NEW CAPTION",
                    });
                    return d;
                  })
                }
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-cyan-400"
              >
                <Plus className="h-3.5 w-3.5" /> Add Caption Cue
              </button>
            </div>
          )}

          {tab === "effects" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <label className="text-xs text-slate-400">
                  Editing Style Preset
                  <select
                    value={timeline.preset}
                    onChange={(e) => updateTl((d) => ({ ...d, preset: e.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                  >
                    {presets.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-slate-400">
                  AI Editing Intensity
                  <select
                    value={timeline.intensity}
                    onChange={(e) => updateTl((d) => ({ ...d, intensity: e.target.value }))}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                  >
                    {intensities.map((it) => (
                      <option key={it} value={it}>
                        {it}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block text-xs text-slate-400">
                Opening Hook Banner (First 1–3s)
                <input
                  type="text"
                  value={timeline.hook_text}
                  onChange={(e) => updateTl((d) => ({ ...d, hook_text: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Intro Title Card Text (First 1.5s)
                <input
                  type="text"
                  value={timeline.intro_text}
                  onChange={(e) => updateTl((d) => ({ ...d, intro_text: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Outro Call-To-Action Text (Last 1.8s)
                <input
                  type="text"
                  value={timeline.outro_text}
                  onChange={(e) => updateTl((d) => ({ ...d, outro_text: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
            </div>
          )}

          {tab === "audio" && (
            <div className="space-y-4">
              <label className="block text-xs text-slate-400">
                Dialogue Volume ({Math.round(timeline.dialogue_volume * 100)}%)
                <input
                  type="range"
                  min={0}
                  max={200}
                  value={Math.round(timeline.dialogue_volume * 100)}
                  onChange={(e) => updateTl((d) => ({ ...d, dialogue_volume: Number(e.target.value) / 100 }))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Background Music Volume ({Math.round(timeline.music_volume * 100)}%)
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(timeline.music_volume * 100)}
                  onChange={(e) => updateTl((d) => ({ ...d, music_volume: Number(e.target.value) / 100 }))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Sound Effects Volume ({Math.round(timeline.sfx_volume * 100)}%)
                <input
                  type="range"
                  min={0}
                  max={150}
                  value={Math.round(timeline.sfx_volume * 100)}
                  onChange={(e) => updateTl((d) => ({ ...d, sfx_volume: Number(e.target.value) / 100 }))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Copyright-Safe Music Track
                <select
                  value={timeline.music_track}
                  onChange={(e) => updateTl((d) => ({ ...d, music_track: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                >
                  {musicTracks.map((tr) => (
                    <option key={tr} value={tr}>
                      {tr}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap gap-5 pt-2 text-xs font-semibold text-slate-200">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={timeline.enable_music}
                    onChange={(e) => updateTl((d) => ({ ...d, enable_music: e.target.checked }))}
                    className="accent-cyan-400"
                  />
                  Enable Ducked Music
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={timeline.enable_sfx}
                    onChange={(e) => updateTl((d) => ({ ...d, enable_sfx: e.target.checked }))}
                    className="accent-cyan-400"
                  />
                  Enable Sound Effects
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={timeline.enable_noise_reduction}
                    onChange={(e) => updateTl((d) => ({ ...d, enable_noise_reduction: e.target.checked }))}
                    className="accent-cyan-400"
                  />
                  Voice Noise Reduction
                </label>
              </div>
            </div>
          )}

          {tab === "score" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4">
                <div className="text-lg font-extrabold text-emerald-400">
                  AI Engagement Potential Score: {clip.breakdown.total_score.toFixed(1)} / 100
                </div>
                <p className="mt-1 text-sm text-slate-300">{clip.breakdown.explanation}</p>
              </div>
              <div className="space-y-2.5">
                {[
                  ["Opening Hook", clip.breakdown.opening_hook],
                  ["Emotional Intensity", clip.breakdown.emotional_intensity],
                  ["Audio Excitement", clip.breakdown.audio_excitement],
                  ["Visual Engagement", clip.breakdown.visual_engagement],
                  ["Live Chat Activity", clip.breakdown.chat_activity ?? 0],
                  ["Content Clarity", clip.breakdown.content_clarity],
                  ["Pacing", clip.breakdown.pacing],
                ].map(([lbl, val]) => (
                  <div key={String(lbl)}>
                    <div className="mb-1 flex justify-between text-xs text-slate-300">
                      <span>{lbl}</span>
                      <span className="font-bold">{Number(val).toFixed(1)}/100</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-400 to-violet-500"
                        style={{ width: `${Math.min(100, Math.max(0, Number(val)))}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
