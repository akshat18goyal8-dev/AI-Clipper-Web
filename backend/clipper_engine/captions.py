"""Dynamic word-by-word animated ASS caption generator (English + Hindi support)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from .models import CaptionCue, CaptionStyle, TranscriptSegment, WordTimestamp


def _hex_to_ass_bgr(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &H00BBGGRR format."""
    c = hex_color.lstrip("#")
    if len(c) != 6:
        return "&H00FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def _format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def build_caption_cues(
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    style: CaptionStyle,
) -> List[CaptionCue]:
    """Group Whisper word-level timestamps into punchy 2-4 word animated cues."""
    clip_words: List[WordTimestamp] = []
    for seg in segments:
        if seg.end < clip_start or seg.start > clip_end:
            continue
        if seg.words:
            for w in seg.words:
                if w.end >= clip_start and w.start <= clip_end:
                    clip_words.append(
                        WordTimestamp(
                            word=w.word.strip(),
                            start=max(0.0, round(w.start - clip_start, 3)),
                            end=max(0.05, round(min(clip_end, w.end) - clip_start, 3)),
                            probability=w.probability,
                            is_emphasis=w.is_emphasis,
                        )
                    )
        else:
            # Fallback word split when word timestamps weren't emitted
            tokens = seg.text.strip().split()
            if tokens:
                s0 = max(0.0, seg.start - clip_start)
                s1 = max(s0 + 0.2, min(clip_end, seg.end) - clip_start)
                step = (s1 - s0) / len(tokens)
                for idx, tok in enumerate(tokens):
                    clip_words.append(
                        WordTimestamp(
                            word=tok,
                            start=round(s0 + idx * step, 3),
                            end=round(s0 + (idx + 1) * step, 3),
                            is_emphasis=tok.endswith("!") or tok.isupper(),
                        )
                    )

    cues: List[CaptionCue] = []
    max_w = max(1, style.max_words_per_cue)
    i = 0
    while i < len(clip_words):
        chunk = clip_words[i : i + max_w]
        # Break early at sentence-ending punctuation
        for j, w in enumerate(chunk):
            if j > 0 and w.word.endswith((".", "!", "?", "।")):
                chunk = chunk[: j + 1]
                break
        i += len(chunk)

        words_text = [w.word for w in chunk]
        raw_text = " ".join(words_text)
        if style.uppercase and not _contains_devanagari(raw_text):
            words_text = [t.upper() for t in words_text]
            raw_text = raw_text.upper()

        highlights = [idx for idx, w in enumerate(chunk) if w.is_emphasis]
        if not highlights and len(chunk) > 0:
            # Highlight longest/most impactful word in the phrase
            highlights = [max(range(len(chunk)), key=lambda idx: len(chunk[idx].word))]

        cues.append(
            CaptionCue(
                id=f"cue_{uuid.uuid4().hex[:6]}",
                start=chunk[0].start,
                end=max(chunk[0].start + 0.25, chunk[-1].end),
                text=raw_text,
                words=chunk,
                highlight_indices=highlights,
                position_y=1440,
            )
        )
    return cues


def write_ass_subtitles(
    cues: List[CaptionCue],
    style: CaptionStyle,
    out_ass_path: str | Path,
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """Render dynamic ASS subtitle file with pop/bounce animations and word-level color highlights."""
    all_text = " ".join(c.text for c in cues)
    font_name = "Noto Sans Devanagari" if _contains_devanagari(all_text) else style.font_name
    primary = _hex_to_ass_bgr(style.primary_color)
    highlight = _hex_to_ass_bgr(style.highlight_color)
    outline = _hex_to_ass_bgr(style.outline_color)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DynamicCap,{font_name},{style.font_size},{primary},{highlight},{outline},&H80000000,-1,0,0,0,100,100,1,0,1,{style.outline_width},{style.shadow_depth},2,60,60,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines: List[str] = [header]
    for cue in cues:
        pos_x = video_width // 2
        pos_y = max(300, min(video_height - 200, cue.position_y))
        anim_tag = f"\\pos({pos_x},{pos_y})"
        if style.animation == "pop":
            anim_tag += "\\fscx82\\fscy82\\t(0,95,\\fscx108\\fscy108)\\t(95,180,\\fscx100\\fscy100)"
        elif style.animation == "bounce":
            anim_tag += "\\fscx75\\fscy115\\t(0,110,\\fscx106\\fscy96)\\t(110,200,\\fscx100\\fscy100)"
        elif style.animation == "slide":
            anim_tag += f"\\move({pos_x},{pos_y + 28},{pos_x},{pos_y},0,140)\\fad(90,60)"
        else:
            anim_tag += "\\fad(120,100)"

        # If we have word timestamps, emit per-word active highlight beats so each word pops in sync!
        if cue.words and len(cue.words) > 1:
            cue_words = cue.text.split()
            for active_idx, w in enumerate(cue.words):
                w_start = max(cue.start, w.start)
                w_end = cue.words[active_idx + 1].start if active_idx + 1 < len(cue.words) else cue.end
                w_end = max(w_start + 0.08, w_end)

                styled_tokens: List[str] = []
                for idx, tok in enumerate(cue_words):
                    safe_tok = tok.replace("{", "(").replace("}", ")")
                    if idx == active_idx:
                        styled_tokens.append(f"{{\\c{highlight}\\fscx110\\fscy110}}{safe_tok}{{\\c{primary}\\fscx100\\fscy100}}")
                    elif idx in cue.highlight_indices:
                        styled_tokens.append(f"{{\\c{highlight}}}{safe_tok}{{\\c{primary}}}")
                    else:
                        styled_tokens.append(safe_tok)

                # Automatic line break every 2 words for mobile readability
                if len(styled_tokens) >= 3:
                    mid = (len(styled_tokens) + 1) // 2
                    rendered_text = " ".join(styled_tokens[:mid]) + "\\N" + " ".join(styled_tokens[mid:])
                else:
                    rendered_text = " ".join(styled_tokens)

                beat_tag = anim_tag if active_idx == 0 else f"\\pos({pos_x},{pos_y})"
                lines.append(
                    f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},DynamicCap,,0,0,0,,{{{beat_tag}}}{rendered_text}\n"
                )
        else:
            safe_txt = cue.text.replace("{", "(").replace("}", ")")
            lines.append(
                f"Dialogue: 0,{_format_ass_time(cue.start)},{_format_ass_time(cue.end)},DynamicCap,,0,0,0,,{{{anim_tag}}}{safe_txt}\n"
            )

    out_path = Path(out_ass_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return str(out_path.resolve())
