# Interview summary method (client-neutral)

Ported from a client's industry-interviews agent on 11 Nov 2026. The project's topics and output folder are in `projects.json` → `interviews`. Run `scripts/interview.py topics <slug>` to see them.

## Picking interviews
- Pick speakers from the client's industry first: artists, producers, engineers, educators and songwriters for music clients. Pick a scientist only when the conversation is about that industry's people or their creative work.
- Prefer long-form conversations (podcasts, talks, masterclasses) over clips and compilations. **Never use re-uploads, "best of" edits or channels that cut up other people's interviews.** Use the original channel.
- Run `interview.py check <slug> "<speaker>"` first. Don't repeat a speaker inside `repeat_weeks`.
- The captions must exist in the project's languages.

## Watching
- Run `interview.py fetch <slug> "<url>" <speaker-topic-slug>`. It writes `transcript.md` and `info.json` and downloads no video.
- Read long transcripts in parts. Don't skim the first 20 minutes and guess the rest.
- Frames are rarely worth it for talking heads. If something on screen matters, `tools/vendor/claude-watch/scripts/watch.py` can pull frames (it needs ffmpeg and yt-dlp: use `source bin/env.sh`).

## Output: `<interview folder>/summary.md`
```
# <Speaker>: <interview title>
Source: <channel>, <upload date>, <length>, <URL>
Watched: <date> · Topics hit: <the project's topics, marked>

## In one paragraph
Your own words: what this conversation is about and why it's useful for this client.

## What they said, by topic
Under each topic heading, 2–5 points in your own words. Each point gets a timestamp (MM:SS or H:MM:SS) and a link (<url>&t=<seconds>s).

## Quote candidates (6, so the client's marketer can pick 4)
Carousels use verbatim quotes only, never paraphrase. For each candidate give:
- the exact words, **under 15 words**
- the timestamp and the t= link
- one line on why it works on its own
Copy the words exactly as the captions give them. Mark `[check audio]` where the auto-captions look misheard.
Never stitch two sentences together or tidy the grammar. If a quote doesn't stand up as said, pick another.

## Carousel angle
One sentence: the single idea a 5-slide quote carousel could hang on.

## Cautions
List anything sensitive: drugs, religion, health claims, swearing, brand deals, or anything that sounds like a promise of results. Also list anything that could read as the speaker endorsing the client (they don't).
```
Then run `interview.py index <slug> "<folder>" --speaker "<name (host: …)>" --topics "<topics hit>"`.

## Rules
- Accuracy comes first. Every point carries a timestamp. Never invent or "improve" a quote. Never attribute a line to the wrong speaker: keep the interviewer and the guest apart.
- Quotes are short excerpts for commentary, always credited. Give at most 6 candidates per interview, each under 15 words, always with the speaker's name and the source. Never paste long stretches of transcript into a summary.
- Transcripts and caption files stay in the interview folder. They are never published.
- Never link a speaker to the client. Some clients may never be named in a summary at all: check `CLAUDE.local.md`.
- The agent never writes post captions, contacts anyone, or touches Buffer. The client's marketer turns the summary into a carousel.
