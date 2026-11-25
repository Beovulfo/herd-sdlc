# Demo script: X, Bluesky and LinkedIn

Length: 45 seconds. Footage: `assets/demo.gif`. Week 3. An AI drafted this.

**What the GIF is:** a real session with Herd 0.3.2 and Claude Sonnet 5.5, sped up. It shows a review step that Herd removed in 0.13.0. Say this in the post. If the GIF is re-recorded in week 0 or later, redo the timings below.

## Cut

The GIF runs 53.5 seconds and holds its last frame at the end. Keep the first 45 seconds. Upload as video, in a private folder:

```bash
out="$(mktemp -d)/demo.mp4"
ffmpeg -i assets/demo.gif -t 45 -pix_fmt yuv420p -vf "scale=960:-2" "$out"
echo "$out"
```

## On-screen text

The GIF already has captions. Add these only as a voice-over or as alt text. Times are seconds, worked out from `assets/demo/phases.json` and `assets/demo/make_demo.py`; check them against the cut.

| From | To | Line |
| --- | --- | --- |
| 0 | 4 | One message: add `slugify` to a file, with two examples. |
| 4 | 7 | Herd starts a task and keeps the request word for word. |
| 7 | 13 | It turns the request into criteria, each with a command. |
| 13 | 16 | The checks run before any code. They fail. |
| 16 | 18 | It writes the code. |
| 18 | 23 | It tries to break the code, and sends it to review. |
| 23 | 31 | The agent tries to finish. The Stop hook blocks it. |
| 31 | 38 | Review finds a real bug: Greek, Cyrillic and CJK titles raised errors. |
| 38 | 45 | Fixed, verified, and a report of what was proven and what was not. |

## Post text

### X

Check the character limit of your account before posting.

> An agent saying "done" is not proof. Herd, my Claude Code plugin, makes it run checks first. Real session, sped up (Herd 0.3.2, Sonnet 5.5; the review step shown is since removed). Open source: https://github.com/Beovulfo/herd-sdlc

### Bluesky

Check the character limit before posting.

> My Claude Code plugin, Herd: checks first, code second, and a Stop hook when the agent tries to finish too early. Recorded with Herd 0.3.2 and Sonnet 5.5, sped up. https://github.com/Beovulfo/herd-sdlc

### LinkedIn

> I built Herd, an open source plugin for Claude Code.
>
> You give a goal. The agent writes success criteria with runnable checks, builds, tries to break its own work, and hands back evidence. A Stop hook sends it back, up to 3 times, while a check is failing.
>
> The video is a real session, sped up, with Herd 0.3.2 and Claude Sonnet 5.5. Current versions no longer have the review step you see.
>
> A weak check still passes weakly, so read the checks.
>
> https://github.com/Beovulfo/herd-sdlc

## Alt text

A terminal recording of a Claude Code session. A panel above it lights each step: intake, criteria, red first, build, break it, review, verify, evidence. The Stop hook blocks one early finish.
