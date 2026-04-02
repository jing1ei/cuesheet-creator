# Field Templates

## General field conventions

- Each row represents a shot block, not a per-cut entry.
- Time fields use `HH:MM:SS.mmm` format.
- `keyframe` points to the representative screenshot path.
- Low-confidence content must go into `confidence` and `needs_confirmation`.
- For unconfirmed names, use "temp: xxx" format.

## A. script template

For early-stage discussion and story breakdown.

| Field | Description |
|---|---|
| shot_block | Block ID, e.g., A1 / B2 |
| start_time | Start time |
| end_time | End time |
| scene | Scene name or temp name |
| location | Location / space |
| characters | Characters present |
| event | Main event in this block |
| important_dialogue | Key dialogue / narration |
| confidence | Confidence summary |
| needs_confirmation | Items pending confirmation |

script perspective:

- State what happens first.
- Then state who is present and where.
- Do not overload with camera technical information.

## B. production template (default)

For director, producer, art, cinematography, and sound cross-department collaboration.

| Field | Description |
|---|---|
| shot_block | Block ID |
| start_time | Start time |
| end_time | End time |
| keyframe | Representative frame screenshot |
| shot_size | Shot size (WS / MS / CU etc.) |
| angle_or_lens | Camera angle / lens character |
| motion | Camera movement |
| scene | Scene / setup |
| mood | Emotional tone |
| location | Location / space |
| characters | Characters present |
| event | Block event |
| important_dialogue | Key dialogue |
| music_note | Music suggestion |
| director_note | Director / production notes |
| confidence | Confidence summary |
| needs_confirmation | Items pending confirmation |

production perspective:

- Prioritize "what needs cross-department alignment in this segment."
- Clarify space, composition, relationships, execution risks.
- `director_note`: camera language and production coordination points — no vague commentary.

## C. music-director template

For composer / scoring communication.

| Field | Description |
|---|---|
| shot_block | Block ID |
| start_time | Start time |
| end_time | End time |
| mood | Emotional tone |
| event | Main event |
| important_dialogue | Key dialogue |
| music_note | Music suggestion |
| rhythm_change | Rhythm change points |
| instrumentation | Instrumentation suggestion |
| dynamics | Dynamic suggestion |
| confidence | Confidence summary |
| needs_confirmation | Items pending confirmation |

music-director perspective:

- Judge mood and rhythmic function first.
- Specify music entry, change, and exit points.
- Instrumentation suggestions should be concrete, e.g., "pizzicato bass + granular electronic pulse."

## Naming confirmation table fields

### Characters

| temporary_name | evidence | confidence | confirmed_name | status |
|---|---|---|---|---|
| temp: Girl-A | red jacket, long hair, main POV in first block | medium | | pending |

### Scenes

| temporary_setup | space_note | confidence | confirmed_setup | status |
|---|---|---|---|---|
| temp: Corridor-1 | white ceiling lights, long straight corridor | medium | | pending |

### Props

| temporary_prop | importance | evidence | confirmed_prop | status |
|---|---|---|---|---|
| temp: Box-A | key-prop | featured in multiple close-ups and handoffs | | pending |

## Final JSON structure

```json
{
  "template": "production",
  "video_title": "sample",
  "source_path": "path/to/video.mp4",
  "rows": [
    {
      "shot_block": "A1",
      "start_time": "00:00:00.000",
      "end_time": "00:00:08.400",
      "keyframe": "keyframes/A1.jpg",
      "shot_size": "WS",
      "angle_or_lens": "front / centered",
      "motion": "slow push-in",
      "scene": "temp: Main Hall",
      "mood": "establishing, solemn, expectant",
      "location": "interior main hall",
      "characters": "temp: Girl-A; extras",
      "event": "Establish main space and introduce central character",
      "important_dialogue": "Narrator: Welcome to...",
      "music_note": "thin pad + light pulse, prepare shift at 8.4s",
      "director_note": "Composition emphasizes depth; watch crowd blocking and center axis",
      "confidence": "segment=high; names=low",
      "needs_confirmation": "character official names; main hall setup name"
    }
  ]
}
```

## Keyframe selection principles

Within the same shot block, prioritize:

1. Frame that best illustrates the dominant composition
2. Frame that best shows character relationships
3. Frame that best shows key actions or key props
4. For transition blocks, prioritize the frame with the clearest visual format
