"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Clapperboard,
  Download,
  Film,
  History,
  LayoutDashboard,
  LogOut,
  PlusCircle,
  Radio,
  Settings,
  Sliders,
  Trash2,
  Upload,
} from "lucide-react";
import ClipEditor from "@/components/ClipEditor";
import { API_BASE, ClipItem, apiFetch, getToken, setToken } from "@/lib/api";

type NavPage = "dashboard" | "new" | "live" | "clips" | "editor" | "exports" | "settings";

interface UserProfile {
  id: string;
  email: string;
  full_name: string;
}

export default function HomePage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [authError, setAuthError] = useState("");

  const [nav, setNav] = useState<NavPage>("dashboard");
  const [presets, setPresets] = useState<string[]>([
    "Gaming Viral Style",
    "High-Energy Creator Style",
    "Podcast Professional Style",
    "Cinematic Documentary Style",
    "Minimal Clean Style",
    "Meme and Comedy Style",
    "Educational Creator Style",
  ]);
  const [intensities, setIntensities] = useState<string[]>(["MINIMAL", "MODERATE", "HIGH ENERGY", "VIRAL STYLE"]);
  const [categories, setCategories] = useState<string[]>([
    "Gaming",
    "Podcasts",
    "Education",
    "Entertainment",
    "Interviews",
    "Reactions",
    "General Videos",
  ]);
  const [musicTracks, setMusicTracks] = useState<string[]>([
    "energetic_pulse",
    "cyber_drive",
    "lofi_focus",
    "cinematic_ambient",
    "upbeat_groove",
  ]);

  const [dashboard, setDashboard] = useState<{
    stats: { projects: number; clips: number; exports: number; avg_score: number; encoder: string; whisper_device: string };
    recent_projects: Array<{
      id: string;
      title: string;
      platform: string;
      category: string;
      preset: string;
      status: string;
      progress: number;
      status_message: string;
    }>;
    top_clips: Array<{ clip_id: string; title: string; score: number; duration: number; category: string }>;
  } | null>(null);

  const [clips, setClips] = useState<ClipItem[]>([]);
  const [selectedClipIds, setSelectedClipIds] = useState<string[]>([]);
  const [activeClip, setActiveClip] = useState<ClipItem | null>(null);
  const [exportsList, setExportsList] = useState<
    Array<{ export_id: string; title: string; width: number; height: number; duration: number; encoder_used: string; created_at: string }>
  >([]);

  // New project state
  const [inputTab, setInputTab] = useState<"file" | "url">("file");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [projCategory, setProjCategory] = useState("General Videos");
  const [projPreset, setProjPreset] = useState("High-Energy Creator Style");
  const [projIntensity, setProjIntensity] = useState("HIGH ENERGY");
  const [projDuration, setProjDuration] = useState<string>("");
  const [projMaxClips, setProjMaxClips] = useState(4);
  const [projLang, setProjLang] = useState("auto");
  const [projMusic, setProjMusic] = useState(true);
  const [projSfx, setProjSfx] = useState(true);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<{ progress: number; message: string; status: string } | null>(null);

  // Live monitor state
  const [liveUrl, setLiveUrl] = useState("");
  const [liveCategory, setLiveCategory] = useState("Gaming");
  const [livePreset, setLivePreset] = useState("Gaming Viral Style");
  const [liveIntensity, setLiveIntensity] = useState("HIGH ENERGY");
  const [liveBuffer, setLiveBuffer] = useState(120);
  const [liveSensitivity, setLiveSensitivity] = useState(65);
  const [liveTel, setLiveTel] = useState<{
    active: boolean;
    audio_score: number;
    visual_score: number;
    chat_score: number | null;
    combined_score: number;
    status_text: string;
    chat_status: string;
    buffered_segments: number;
  } | null>(null);

  // Settings state
  const [settingsForm, setSettingsForm] = useState({
    whisper_model: "base",
    use_gpu: true,
    default_preset: "High-Energy Creator Style",
    default_intensity: "HIGH ENERGY",
    default_category: "General Videos",
    enable_music: true,
    enable_sfx: true,
    youtube_api_key: "",
    twitch_client_id: "",
    twitch_oauth_token: "",
  });
  const [settingsSavedMsg, setSettingsSavedMsg] = useState("");

  const loadHealthAndMe = useCallback(async () => {
    try {
      const h = await apiFetch<{
        presets: string[];
        intensities: string[];
        categories: string[];
        music_tracks: string[];
      }>("/api/health");
      if (h.presets?.length) setPresets(h.presets);
      if (h.intensities?.length) setIntensities(h.intensities);
      if (h.categories?.length) setCategories(h.categories);
      if (h.music_tracks?.length) setMusicTracks(h.music_tracks);
    } catch {}

    if (!getToken()) return;
    try {
      const me = await apiFetch<UserProfile>("/api/auth/me");
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    }
  }, []);

  const refreshWorkspace = useCallback(async () => {
    if (!getToken()) return;
    try {
      const [dash, clipsData, expData, setData] = await Promise.all([
        apiFetch<typeof dashboard>("/api/dashboard"),
        apiFetch<ClipItem[]>("/api/clips"),
        apiFetch<typeof exportsList>("/api/exports"),
        apiFetch<{
          whisper_model: string;
          use_gpu: boolean;
          default_preset: string;
          default_intensity: string;
          default_category: string;
          enable_music: boolean;
          enable_sfx: boolean;
          twitch_client_id: string;
        }>("/api/settings"),
      ]);
      setDashboard(dash);
      setClips(clipsData);
      setExportsList(expData);
      setSettingsForm((prev) => ({
        ...prev,
        whisper_model: setData.whisper_model,
        use_gpu: setData.use_gpu,
        default_preset: setData.default_preset,
        default_intensity: setData.default_intensity,
        default_category: setData.default_category,
        enable_music: setData.enable_music,
        enable_sfx: setData.enable_sfx,
        twitch_client_id: setData.twitch_client_id || "",
      }));
    } catch {}
  }, []);

  useEffect(() => {
    loadHealthAndMe();
  }, [loadHealthAndMe]);

  useEffect(() => {
    if (user) refreshWorkspace();
  }, [user, refreshWorkspace]);

  // Poll active project progress
  useEffect(() => {
    if (!activeJobId) return;
    const iv = setInterval(async () => {
      try {
        const res = await apiFetch<{ status: string; progress: number; status_message: string }>(`/api/projects/${activeJobId}`);
        setJobProgress({ progress: res.progress, message: res.status_message, status: res.status });
        if (res.status === "completed" || res.status === "failed") {
          clearInterval(iv);
          setActiveJobId(null);
          await refreshWorkspace();
          if (res.status === "completed") setNav("clips");
        }
      } catch {
        clearInterval(iv);
      }
    }, 1500);
    return () => clearInterval(iv);
  }, [activeJobId, refreshWorkspace]);

  // Poll live telemetry when monitoring
  useEffect(() => {
    if (nav !== "live" && !liveTel?.active) return;
    const iv = setInterval(async () => {
      try {
        const tel = await apiFetch<typeof liveTel>("/api/live/status");
        setLiveTel(tel);
        if (tel?.active) refreshWorkspace();
      } catch {}
    }, 2000);
    return () => clearInterval(iv);
  }, [nav, liveTel?.active, refreshWorkspace]);

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      const body = authMode === "login" ? { email, password } : { email, full_name: fullName, password };
      const res = await apiFetch<{ access_token: string; user: UserProfile }>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setToken(res.access_token);
      setUser(res.user);
    } catch (err: unknown) {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    }
  };

  const handleStartProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setJobProgress({ progress: 0.02, message: "Submitting project...", status: "queued" });
      if (inputTab === "file") {
        if (!uploadFile) throw new Error("Choose a video file to upload.");
        const fd = new FormData();
        fd.append("file", uploadFile);
        fd.append("category", projCategory);
        fd.append("preset", projPreset);
        fd.append("intensity", projIntensity);
        if (projDuration) fd.append("preferred_duration", projDuration);
        fd.append("max_clips", String(projMaxClips));
        fd.append("language", projLang);
        fd.append("enable_music", String(projMusic));
        fd.append("enable_sfx", String(projSfx));
        const res = await apiFetch<{ project_id: string }>("/api/projects/upload", { method: "POST", body: fd });
        setActiveJobId(res.project_id);
      } else {
        if (!sourceUrl.trim()) throw new Error("Enter a supported video URL.");
        const res = await apiFetch<{ project_id: string }>("/api/projects/url", {
          method: "POST",
          body: JSON.stringify({
            source_url: sourceUrl.trim(),
            category: projCategory,
            preset: projPreset,
            intensity: projIntensity,
            preferred_duration: projDuration ? Number(projDuration) : null,
            max_clips: projMaxClips,
            language: projLang,
            enable_music: projMusic,
            enable_sfx: projSfx,
          }),
        });
        setActiveJobId(res.project_id);
      }
    } catch (err: unknown) {
      setJobProgress({
        progress: 0,
        message: err instanceof Error ? err.message : "Submission failed",
        status: "failed",
      });
    }
  };

  const handleBatchExport = async () => {
    if (!selectedClipIds.length) return;
    const token = getToken();
    const resp = await fetch(`${API_BASE}/api/clips/batch-export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ clip_ids: selectedClipIds }),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ai_clipper_batch.zip";
    a.click();
    URL.revokeObjectURL(url);
    refreshWorkspace();
  };

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070B14] px-4">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#0E1525] p-8 shadow-2xl">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 text-white">
              <Clapperboard className="h-6 w-6" />
            </div>
            <h1 className="text-2xl font-extrabold text-white">AI CLIPPER 2.0</h1>
            <p className="text-xs font-semibold tracking-widest text-cyan-400">WEB STUDIO</p>
          </div>

          <div className="mb-5 grid grid-cols-2 gap-2 rounded-xl bg-[#070B14] p-1">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setAuthMode(m)}
                className={`rounded-lg py-2 text-xs font-bold capitalize transition ${
                  authMode === m ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white"
                }`}
              >
                {m === "login" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <form onSubmit={handleAuthSubmit} className="space-y-4">
            {authMode === "register" && (
              <input
                type="text"
                placeholder="Full Name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full rounded-xl border border-slate-700 bg-[#070B14] px-4 py-2.5 text-sm text-white focus:border-cyan-400 focus:outline-none"
              />
            )}
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-xl border border-slate-700 bg-[#070B14] px-4 py-2.5 text-sm text-white focus:border-cyan-400 focus:outline-none"
            />
            <input
              type="password"
              placeholder="Password (min 6 chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-xl border border-slate-700 bg-[#070B14] px-4 py-2.5 text-sm text-white focus:border-cyan-400 focus:outline-none"
            />
            {authError && <p className="text-xs font-medium text-rose-400">{authError}</p>}
            <button
              type="submit"
              className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 py-2.5 text-sm font-bold text-white shadow-lg hover:opacity-95"
            >
              {authMode === "login" ? "Sign In to Studio" : "Create Studio Account"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  const navItems: Array<{ id: NavPage; label: string; icon: React.ReactNode }> = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
    { id: "new", label: "New Project", icon: <PlusCircle className="h-4 w-4" /> },
    { id: "live", label: "Live Stream Monitor", icon: <Radio className="h-4 w-4" /> },
    { id: "clips", label: "My Clips", icon: <Film className="h-4 w-4" /> },
    { id: "editor", label: "Clip Editor", icon: <Sliders className="h-4 w-4" /> },
    { id: "exports", label: "Export History", icon: <History className="h-4 w-4" /> },
    { id: "settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  ];

  const token = getToken() || "";

  return (
    <div className="flex min-h-screen bg-[#070B14] text-slate-100">
      {/* Sidebar */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800/80 bg-[#0B101D] p-5">
        <div className="mb-8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 text-white">
              <Clapperboard className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-extrabold tracking-tight text-white">AI CLIPPER 2.0</h1>
              <p className="text-[10px] font-bold tracking-widest text-cyan-400">WEB STUDIO</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1.5">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setNav(item.id)}
              className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition ${
                nav === item.id
                  ? "bg-gradient-to-r from-blue-600 to-violet-600 text-white shadow"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="mt-6 border-t border-slate-800 pt-4">
          <p className="truncate text-xs font-semibold text-slate-300">{user.full_name}</p>
          <p className="truncate text-[11px] text-slate-500">{user.email}</p>
          <button
            onClick={() => {
              setToken(null);
              setUser(null);
            }}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-800 bg-slate-900 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800"
          >
            <LogOut className="h-3.5 w-3.5" /> Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-6 lg:p-8">
        {nav === "dashboard" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-extrabold text-white">Dashboard</h2>
                <p className="text-sm text-slate-400">Multi-signal AI highlight extraction & pro vertical video editing</p>
              </div>
              <button
                onClick={() => setNav("new")}
                className="rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 px-5 py-2.5 text-sm font-bold text-white shadow hover:opacity-95"
              >
                + New AI Clip Project
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["TOTAL PROJECTS", dashboard?.stats.projects ?? 0, "Uploads, URLs & Live"],
                ["CLIPS GENERATED", dashboard?.stats.clips ?? 0, "9:16 Edited Reels"],
                ["AVG SCORE", dashboard?.stats.avg_score ?? 0, "0–100 Engagement Rating"],
                ["ENCODER", (dashboard?.stats.encoder ?? "libx264").toUpperCase(), `Whisper: ${dashboard?.stats.whisper_device ?? "cpu"}`],
              ].map(([lbl, val, sub]) => (
                <div key={String(lbl)} className="rounded-2xl border border-slate-800 bg-[#0E1525] p-5">
                  <p className="text-xs font-bold text-slate-400">{lbl}</p>
                  <p className="mt-1 text-3xl font-extrabold text-cyan-400">{val}</p>
                  <p className="mt-1 text-xs text-slate-500">{sub}</p>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-slate-800 bg-[#0E1525] p-5">
              <h3 className="mb-3 text-sm font-bold text-white">Recent Processing Jobs</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-800 text-xs text-slate-400">
                    <tr>
                      <th className="py-2">Project</th>
                      <th className="py-2">Platform</th>
                      <th className="py-2">Category</th>
                      <th className="py-2">Progress</th>
                      <th className="py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {(dashboard?.recent_projects || []).map((p) => (
                      <tr key={p.id}>
                        <td className="py-2.5 font-medium text-slate-200">{p.title}</td>
                        <td className="py-2.5 text-slate-400">{p.platform}</td>
                        <td className="py-2.5 text-slate-400">{p.category}</td>
                        <td className="py-2.5 text-cyan-400">{Math.round(p.progress * 100)}%</td>
                        <td className="py-2.5 text-xs text-slate-300">{p.status.toUpperCase()} — {p.status_message}</td>
                      </tr>
                    ))}
                    {!dashboard?.recent_projects?.length && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-slate-500">
                          No projects yet. Create a New Project to begin!
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {nav === "new" && (
          <form onSubmit={handleStartProject} className="mx-auto max-w-3xl space-y-6">
            <div>
              <h2 className="text-2xl font-extrabold text-white">New AI Clip Project</h2>
              <p className="text-sm text-slate-400">Upload a video file or paste a supported YouTube, Twitch, or direct video URL.</p>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-[#0E1525] p-5 space-y-4">
              <div className="flex gap-2">
                {(["file", "url"] as const).map((t) => (
                  <button
                    type="button"
                    key={t}
                    onClick={() => setInputTab(t)}
                    className={`rounded-lg px-4 py-2 text-xs font-bold ${
                      inputTab === t ? "bg-blue-600 text-white" : "bg-slate-900 text-slate-400"
                    }`}
                  >
                    {t === "file" ? "Upload Computer Video" : "Paste Video URL"}
                  </button>
                ))}
              </div>

              {inputTab === "file" ? (
                <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700 bg-[#070B14] p-8 text-center hover:border-cyan-400">
                  <Upload className="mb-2 h-8 w-8 text-cyan-400" />
                  <span className="text-sm font-semibold text-white">
                    {uploadFile ? uploadFile.name : "Click to choose MP4, MKV, MOV, or WebM video"}
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  />
                </label>
              ) : (
                <input
                  type="url"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=... or https://www.twitch.tv/videos/..."
                  className="w-full rounded-xl border border-slate-700 bg-[#070B14] px-4 py-3 text-sm text-white focus:border-cyan-400 focus:outline-none"
                />
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 rounded-2xl border border-slate-800 bg-[#0E1525] p-5 sm:grid-cols-2">
              <label className="text-xs text-slate-400">
                Content Category
                <select
                  value={projCategory}
                  onChange={(e) => setProjCategory(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                >
                  {categories.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-400">
                Editing Preset
                <select
                  value={projPreset}
                  onChange={(e) => setProjPreset(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                >
                  {presets.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-400">
                AI Editing Intensity
                <select
                  value={projIntensity}
                  onChange={(e) => setProjIntensity(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                >
                  {intensities.map((it) => (
                    <option key={it}>{it}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-400">
                Target Clip Duration
                <select
                  value={projDuration}
                  onChange={(e) => setProjDuration(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                >
                  <option value="">Auto (AI Optimal ≤ 60s)</option>
                  {[10, 15, 30, 45, 60].map((d) => (
                    <option key={d} value={d}>
                      {d} seconds
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-400">
                Max Clips
                <input
                  type="number"
                  min={1}
                  max={15}
                  value={projMaxClips}
                  onChange={(e) => setProjMaxClips(Number(e.target.value))}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                />
              </label>
              <label className="text-xs text-slate-400">
                Speech Language
                <select
                  value={projLang}
                  onChange={(e) => setProjLang(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2.5 text-sm text-white"
                >
                  <option value="auto">Auto Detect (English / Hindi)</option>
                  <option value="en">English</option>
                  <option value="hi">Hindi</option>
                </select>
              </label>
              <div className="flex items-center gap-6 sm:col-span-2 pt-1 text-xs font-semibold text-slate-200">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={projMusic} onChange={(e) => setProjMusic(e.target.checked)} className="accent-cyan-400" />
                  Background Music (Ducked)
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={projSfx} onChange={(e) => setProjSfx(e.target.checked)} className="accent-cyan-400" />
                  Context-Aware Sound Effects
                </label>
              </div>
            </div>

            {jobProgress && (
              <div className="rounded-2xl border border-cyan-500/30 bg-[#0E1525] p-4 space-y-2">
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-cyan-300">{jobProgress.message}</span>
                  <span>{Math.round(jobProgress.progress * 100)}%</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-400 to-violet-500 transition-all"
                    style={{ width: `${Math.round(jobProgress.progress * 100)}%` }}
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={Boolean(activeJobId)}
              className="rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 px-6 py-3 text-sm font-bold text-white shadow hover:opacity-95 disabled:opacity-50"
            >
              {activeJobId ? "AI Processing Running..." : "Analyze & Generate AI Clips"}
            </button>
          </form>
        )}

        {nav === "live" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-extrabold text-white">Live Stream Intelligence Monitor</h2>
              <p className="text-sm text-slate-400">
                Simultaneous Audio + Visual + Live Chat scoring with rolling buffer highlight capture.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 rounded-2xl border border-slate-800 bg-[#0E1525] p-5 sm:grid-cols-2">
              <input
                type="url"
                value={liveUrl}
                onChange={(e) => setLiveUrl(e.target.value)}
                placeholder="Twitch channel URL, YouTube Live URL, or .m3u8 HLS stream"
                className="sm:col-span-2 rounded-xl border border-slate-700 bg-[#070B14] px-4 py-2.5 text-sm text-white"
              />
              <select
                value={liveCategory}
                onChange={(e) => setLiveCategory(e.target.value)}
                className="rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
              >
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
              <select
                value={livePreset}
                onChange={(e) => setLivePreset(e.target.value)}
                className="rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
              >
                {presets.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <label className="text-xs text-slate-400">
                Rolling Buffer Duration: {liveBuffer}s
                <input
                  type="range"
                  min={40}
                  max={300}
                  value={liveBuffer}
                  onChange={(e) => setLiveBuffer(Number(e.target.value))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <label className="text-xs text-slate-400">
                Sensitivity Threshold: {liveSensitivity}/100
                <input
                  type="range"
                  min={35}
                  max={90}
                  value={liveSensitivity}
                  onChange={(e) => setLiveSensitivity(Number(e.target.value))}
                  className="mt-1 w-full accent-cyan-400"
                />
              </label>
              <div className="flex gap-3 sm:col-span-2">
                <button
                  onClick={async () => {
                    await apiFetch("/api/live/start", {
                      method: "POST",
                      body: JSON.stringify({
                        stream_url: liveUrl,
                        category: liveCategory,
                        preset: livePreset,
                        intensity: liveIntensity,
                        buffer_seconds: liveBuffer,
                        sensitivity: liveSensitivity,
                      }),
                    });
                    const t = await apiFetch<typeof liveTel>("/api/live/status");
                    setLiveTel(t);
                  }}
                  disabled={Boolean(liveTel?.active) || !liveUrl.trim()}
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40"
                >
                  Start Live Monitoring
                </button>
                <button
                  onClick={async () => {
                    await apiFetch("/api/live/stop", { method: "POST" });
                    const t = await apiFetch<typeof liveTel>("/api/live/status");
                    setLiveTel(t);
                  }}
                  disabled={!liveTel?.active}
                  className="rounded-xl border border-rose-500/40 bg-rose-950/40 px-5 py-2.5 text-sm font-bold text-rose-200 disabled:opacity-40"
                >
                  Stop Monitoring
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-[#0E1525] p-5 space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold text-white">
                <Activity className="h-4 w-4 text-cyan-400" /> Real-Time Signal Telemetry
              </div>
              <p className="text-xs text-slate-400">
                Status: {liveTel?.status_text || "Idle"} | Chat: {liveTel?.chat_status || "Waiting"} | Buffered segments:{" "}
                {liveTel?.buffered_segments || 0}
              </p>
              {[
                ["Audio Excitement", liveTel?.audio_score ?? 0],
                ["Visual Action", liveTel?.visual_score ?? 0],
                ["Live Chat Surge", liveTel?.chat_score ?? 0],
                ["Combined Highlight Score", liveTel?.combined_score ?? 0],
              ].map(([lbl, val]) => (
                <div key={String(lbl)}>
                  <div className="mb-1 flex justify-between text-xs text-slate-300">
                    <span>{lbl}</span>
                    <span>{Number(val).toFixed(1)}/100</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                      style={{ width: `${Math.min(100, Number(val))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {nav === "clips" && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-2xl font-extrabold text-white">My AI Clips</h2>
                <p className="text-sm text-slate-400">Sorted by Engagement Potential Score. Edit, preview, or batch-export ZIP.</p>
              </div>
              <button
                onClick={handleBatchExport}
                disabled={!selectedClipIds.length}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-40"
              >
                <Download className="h-4 w-4" /> Batch Export Selected ({selectedClipIds.length})
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {clips.map((c) => (
                <div key={c.clip_id} className="flex gap-4 rounded-2xl border border-slate-800 bg-[#0E1525] p-4">
                  <div className="flex flex-col items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedClipIds.includes(c.clip_id)}
                      onChange={(e) =>
                        setSelectedClipIds((prev) =>
                          e.target.checked ? [...prev, c.clip_id] : prev.filter((id) => id !== c.clip_id)
                        )
                      }
                      className="accent-cyan-400"
                    />
                    <img
                      src={`${API_BASE}/api/clips/${c.clip_id}/thumbnail?token=${encodeURIComponent(token)}`}
                      alt={c.title}
                      className="h-32 w-20 rounded-lg bg-black object-cover"
                    />
                  </div>
                  <div className="flex flex-1 flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-bold text-white">{c.title}</h3>
                        <span className="shrink-0 rounded-lg border border-emerald-500/40 bg-emerald-950/60 px-2.5 py-0.5 text-xs font-bold text-emerald-300">
                          {c.score.toFixed(1)}/100
                        </span>
                      </div>
                      <p className="mt-1 text-xs font-semibold text-cyan-400">
                        {c.category} • {c.duration.toFixed(1)}s • {c.timeline.preset}
                      </p>
                      <p className="mt-1.5 text-xs text-slate-400 line-clamp-2">{c.explanation}</p>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => {
                          setActiveClip(c);
                          setNav("editor");
                        }}
                        className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-500"
                      >
                        Open in Editor
                      </button>
                      <a
                        href={`${API_BASE}/api/clips/${c.clip_id}/video?token=${encodeURIComponent(token)}`}
                        download={`${c.clip_id}.mp4`}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                      >
                        Download MP4
                      </a>
                      <button
                        onClick={async () => {
                          await apiFetch(`/api/clips/${c.clip_id}`, { method: "DELETE" });
                          refreshWorkspace();
                        }}
                        className="rounded-lg border border-rose-500/30 bg-rose-950/30 px-2.5 py-1.5 text-xs font-semibold text-rose-300"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {!clips.length && (
                <div className="col-span-2 rounded-2xl border border-slate-800 bg-[#0E1525] p-10 text-center text-slate-400">
                  No clips generated yet. Create a New Project to generate AI-edited short-form videos.
                </div>
              )}
            </div>
          </div>
        )}

        {nav === "editor" && (
          <ClipEditor
            clip={activeClip}
            presets={presets}
            intensities={intensities}
            musicTracks={musicTracks}
            onRefresh={refreshWorkspace}
          />
        )}

        {nav === "exports" && (
          <div className="space-y-4">
            <h2 className="text-2xl font-extrabold text-white">Export History</h2>
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-[#0E1525]">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-800 bg-slate-900/50 text-xs text-slate-400">
                  <tr>
                    <th className="p-3">Title</th>
                    <th className="p-3">Resolution</th>
                    <th className="p-3">Duration</th>
                    <th className="p-3">Encoder</th>
                    <th className="p-3">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {exportsList.map((ex) => (
                    <tr key={ex.export_id}>
                      <td className="p-3 font-medium text-white">{ex.title}</td>
                      <td className="p-3 text-slate-300">
                        {ex.width}×{ex.height}
                      </td>
                      <td className="p-3 text-slate-300">{ex.duration.toFixed(1)}s</td>
                      <td className="p-3 text-cyan-400">{ex.encoder_used}</td>
                      <td className="p-3 text-xs text-slate-400">{ex.created_at}</td>
                    </tr>
                  ))}
                  {!exportsList.length && (
                    <tr>
                      <td colSpan={5} className="p-6 text-center text-slate-500">
                        No exports logged yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {nav === "settings" && (
          <div className="mx-auto max-w-2xl space-y-5">
            <h2 className="text-2xl font-extrabold text-white">User Settings</h2>
            <div className="space-y-4 rounded-2xl border border-slate-800 bg-[#0E1525] p-6">
              <label className="block text-xs text-slate-400">
                Whisper ASR Model
                <select
                  value={settingsForm.whisper_model}
                  onChange={(e) => setSettingsForm({ ...settingsForm, whisper_model: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                >
                  {["tiny", "base", "small"].map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                <input
                  type="checkbox"
                  checked={settingsForm.use_gpu}
                  onChange={(e) => setSettingsForm({ ...settingsForm, use_gpu: e.target.checked })}
                  className="accent-cyan-400"
                />
                Enable GPU Hardware Acceleration (with CPU fallback)
              </label>
              <label className="block text-xs text-slate-400">
                YouTube Data API v3 Key (Optional — for YouTube Live Chat Intelligence)
                <input
                  type="password"
                  value={settingsForm.youtube_api_key}
                  onChange={(e) => setSettingsForm({ ...settingsForm, youtube_api_key: e.target.value })}
                  placeholder="Leave blank to keep existing"
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Twitch Client ID (Optional)
                <input
                  type="text"
                  value={settingsForm.twitch_client_id}
                  onChange={(e) => setSettingsForm({ ...settingsForm, twitch_client_id: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Twitch OAuth Token (Optional)
                <input
                  type="password"
                  value={settingsForm.twitch_oauth_token}
                  onChange={(e) => setSettingsForm({ ...settingsForm, twitch_oauth_token: e.target.value })}
                  placeholder="Leave blank to keep existing"
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-[#070B14] px-3 py-2 text-sm text-white"
                />
              </label>
              {settingsSavedMsg && <p className="text-xs font-semibold text-emerald-400">{settingsSavedMsg}</p>}
              <button
                onClick={async () => {
                  await apiFetch("/api/settings", { method: "PUT", body: JSON.stringify(settingsForm) });
                  setSettingsSavedMsg("Settings saved successfully!");
                }}
                className="rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 px-5 py-2.5 text-sm font-bold text-white"
              >
                Save Settings
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
