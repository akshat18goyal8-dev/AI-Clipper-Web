"""Live chat intelligence & platform live chat connectors (Twitch IRC + YouTube Live Chat API)."""

from __future__ import annotations

import re
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

import httpx
import numpy as np

HYPE_TOKENS = {
    "lol", "lmao", "omg", "wtf", "pog", "poggers", "clutch", "insane", "crazy",
    "w", "gg", "rip", "no way", "bro", "haha", "hahaha", "lets go", "sheesh",
    "fire", "goat", "kya", "op", "bawaal", "gazab",
}

EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF]+",
    flags=re.UNICODE,
)


@dataclass
class ChatMessage:
    timestamp: float
    author: str
    text: str


class LiveChatAnalyzer:
    """Computes rolling baseline vs burst excitement score (0..100) from chat messages."""

    def __init__(self, baseline_window_sec: float = 60.0, burst_window_sec: float = 5.0):
        self.baseline_window_sec = baseline_window_sec
        self.burst_window_sec = burst_window_sec
        self._messages: Deque[ChatMessage] = deque(maxlen=5000)
        self._lock = threading.Lock()

    def add_message(self, text: str, author: str = "viewer", timestamp: Optional[float] = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._messages.append(ChatMessage(timestamp=ts, author=author, text=text))

    def get_score_at(self, now_ts: Optional[float] = None) -> Optional[float]:
        now = now_ts if now_ts is not None else time.time()
        with self._lock:
            msgs = [m for m in self._messages if now - m.timestamp <= self.baseline_window_sec]
        if not msgs:
            return None

        burst_msgs = [m for m in msgs if now - m.timestamp <= self.burst_window_sec]
        baseline_rate = max(0.05, len(msgs) / self.baseline_window_sec)
        burst_rate = len(burst_msgs) / self.burst_window_sec
        surge_ratio = burst_rate / baseline_rate  # e.g., 10/min (0.16/s) -> 250/min (4.16/s) => ~25x

        # Rate spike score (log scaled)
        rate_score = min(100.0, np.log1p(max(0.0, surge_ratio - 1.0)) * 32.0 + min(30.0, burst_rate * 6.0))

        # Hype keyword + emoji + repetition score
        if burst_msgs:
            hype_hits = 0
            emoji_hits = 0
            normalized_texts: List[str] = []
            for m in burst_msgs:
                low = m.text.lower()
                tokens = set(re.findall(r"[a-z0-9]+", low))
                if tokens & HYPE_TOKENS or any(k in low for k in ("no way", "lets go")):
                    hype_hits += 1
                if EMOJI_PATTERN.search(m.text):
                    emoji_hits += 1
                normalized_texts.append(re.sub(r"\s+", " ", low.strip()))
            hype_ratio = hype_hits / len(burst_msgs)
            emoji_ratio = emoji_hits / len(burst_msgs)
            unique_ratio = len(set(normalized_texts)) / len(normalized_texts)
            spam_repeat_ratio = 1.0 - unique_ratio
            content_score = min(100.0, hype_ratio * 60.0 + emoji_ratio * 35.0 + spam_repeat_ratio * 45.0)
        else:
            content_score = 0.0

        return float(np.clip(0.62 * rate_score + 0.38 * content_score, 0.0, 100.0))

    def score_timeline(self, times: np.ndarray) -> Optional[np.ndarray]:
        with self._lock:
            if not self._messages:
                return None
        scores = np.zeros(len(times), dtype=np.float32)
        for i, t in enumerate(times):
            val = self.get_score_at(float(t))
            scores[i] = val if val is not None else 0.0
        return scores


class TwitchIRCReader:
    """Connects to Twitch IRC (anonymous justinfan or OAuth) to feed LiveChatAnalyzer."""

    def __init__(self, channel: str, analyzer: LiveChatAnalyzer, oauth_token: Optional[str] = None):
        self.channel = channel.lstrip("#").lower()
        self.analyzer = analyzer
        self.oauth_token = oauth_token
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.status_note = ""

    def start(self) -> None:
        if not self.channel:
            self.status_note = "No Twitch channel name found; chat intelligence disabled."
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            sock = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=10)
            nick = f"justinfan{int(time.time()) % 90000 + 10000}"
            if self.oauth_token:
                tok = self.oauth_token if self.oauth_token.startswith("oauth:") else f"oauth:{self.oauth_token}"
                sock.sendall(f"PASS {tok}\r\n".encode("utf-8"))
            sock.sendall(f"NICK {nick}\r\n".encode("utf-8"))
            sock.sendall(f"JOIN #{self.channel}\r\n".encode("utf-8"))
            sock.settimeout(1.5)
            self.connected = True
            self.status_note = f"Connected to Twitch chat #{self.channel}"
            buf = ""
            while not self._stop_event.is_set():
                try:
                    data = sock.recv(4096).decode("utf-8", errors="ignore")
                    if not data:
                        break
                    buf += data
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        if line.startswith("PING"):
                            sock.sendall("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                        elif "PRIVMSG" in line:
                            m = re.match(r":([^!]+)!.*PRIVMSG #[^ ]+ :(.*)", line)
                            if m:
                                self.analyzer.add_message(author=m.group(1), text=m.group(2))
                except socket.timeout:
                    continue
            sock.close()
        except Exception as exc:
            self.connected = False
            self.status_note = f"Twitch chat unavailable ({exc}); using audio+visual scoring."


class YouTubeLiveChatPoller:
    """Polls YouTube Data API v3 liveChatMessages when YOUTUBE_API_KEY is supplied."""

    def __init__(self, video_id: str, api_key: Optional[str], analyzer: LiveChatAnalyzer):
        self.video_id = video_id
        self.api_key = api_key
        self.analyzer = analyzer
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.status_note = ""

    def start(self) -> None:
        if not self.api_key or not self.video_id:
            self.status_note = "YouTube API key not configured; live chat disabled (audio+visual active)."
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            with httpx.Client(timeout=10.0) as client:
                v_resp = client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "liveStreamingDetails", "id": self.video_id, "key": self.api_key},
                )
                v_data = v_resp.json()
                items = v_data.get("items", [])
                chat_id = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId") if items else None
                if not chat_id:
                    self.status_note = "No active YouTube liveChatId found; using audio+visual scoring."
                    return
                self.connected = True
                self.status_note = "Connected to YouTube Live Chat API"
                page_token = None
                while not self._stop_event.is_set():
                    params: Dict[str, str] = {
                        "liveChatId": chat_id,
                        "part": "snippet,authorDetails",
                        "key": self.api_key or "",
                    }
                    if page_token:
                        params["pageToken"] = page_token
                    resp = client.get("https://www.googleapis.com/youtube/v3/liveChat/messages", params=params)
                    if resp.status_code != 200:
                        self.status_note = f"YouTube Live Chat API returned {resp.status_code}; continuing audio+visual."
                        break
                    data = resp.json()
                    page_token = data.get("nextPageToken")
                    for item in data.get("items", []):
                        txt = item.get("snippet", {}).get("displayMessage", "")
                        author = item.get("authorDetails", {}).get("displayName", "viewer")
                        if txt:
                            self.analyzer.add_message(text=txt, author=author)
                    wait_sec = max(2.0, float(data.get("pollingIntervalMillis", 3000)) / 1000.0)
                    self._stop_event.wait(wait_sec)
        except Exception as exc:
            self.connected = False
            self.status_note = f"YouTube Live Chat polling stopped ({exc}); using audio+visual."
