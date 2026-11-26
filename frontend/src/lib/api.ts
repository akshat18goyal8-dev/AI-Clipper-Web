export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface CaptionCue {
  id: string;
  start: number;
  end: number;
  text: string;
  highlight_indices?: number[];
  position_y?: number;
}

export interface EditTimeline {
  trim_start: number;
  trim_end: number;
  target_width: number;
  target_height: number;
  crop_offset_x: number;
  crop_offset_y: number;
  reframe_mode: string;
  preset: string;
  intensity: string;
  caption_style: {
    font_name: string;
    font_size: number;
    primary_color: string;
    highlight_color: string;
    outline_color: string;
    outline_width: number;
    shadow_depth: number;
    uppercase: boolean;
    animation: string;
    max_words_per_cue: number;
  };
  captions: CaptionCue[];
  hook_text: string;
  intro_text: string;
  outro_text: string;
  dialogue_volume: number;
  music_volume: number;
  sfx_volume: number;
  enable_music: boolean;
  enable_sfx: boolean;
  enable_noise_reduction: boolean;
  music_track: string;
  zoom_keyframes?: unknown[];
  overlays?: unknown[];
  sfx_events?: unknown[];
  dead_air_cuts?: unknown[];
}

export interface ClipItem {
  clip_id: string;
  project_id: string;
  title: string;
  start_time: number;
  end_time: number;
  duration: number;
  category: string;
  language: string;
  transcript_text?: string;
  score: number;
  explanation: string;
  breakdown: {
    opening_hook: number;
    emotional_intensity: number;
    audio_excitement: number;
    visual_engagement: number;
    chat_activity: number | null;
    content_clarity: number;
    pacing: number;
    total_score: number;
    explanation: string;
  };
  timeline: EditTimeline;
  encoder_used: string;
  has_video?: boolean;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("clipper_token");
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("clipper_token", token);
  else localStorage.removeItem("clipper_token");
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!resp.ok) {
    let msg = `Request failed (${resp.status})`;
    try {
      const err = await resp.json();
      msg = err.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return resp.json() as Promise<T>;
}
