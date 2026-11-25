# Launch plan: weeks 0 to 4

Drafts only. Toni publishes everything by hand. Nothing here has been posted or submitted.

## Plan by week

| Week | What | Draft |
| --- | --- | --- |
| Week 0 | Repository work from issue #104: demo, benchmark table in the README, use cases, CONTRIBUTING, issue templates, Discussions, `claude plugin validate --strict`, one launch release | none: done in the repository, not a draft |
| Week 1 | Show HN on a weekday, 12 to 17 UTC | [show-hn.md](show-hn.md) |
| Week 2 | Reddit: r/ClaudeAI and r/ClaudeCode | [r/ClaudeAI](reddit-claudeai.md), [r/ClaudeCode](reddit-claudecode.md) |
| Week 3 | dev.to article | [devto-stop-hook.md](devto-stop-hook.md) |
| Week 3 | Short demo posts on X, Bluesky and LinkedIn | [demo-script.md](demo-script.md) |
| Week 4 | Directory submissions, once eligible | [awesome-claude-code](awesome-claude-code.md), [Claude plugin directory](claude-directory.md) |
| Week 4 | Retro | [week4-retro.md](week4-retro.md) |

## Before week 1

Check each item on the day. Week 0 is tracked in issue #104, not here.

- [ ] Week 0 is merged and CI is green.
- [ ] The launch release is tagged. Note its version: `____`.
- [ ] The install commands in the README work in a clean project.
- [ ] The version in each draft's results is still labelled correctly. Results from an older version stay labelled with that version.
- [ ] If `assets/demo.gif` was re-recorded, update [demo-script.md](demo-script.md).

## Channel rules

Read on 2026-11-25 by a research agent. Rules change: open the source before posting.

### Show HN

Sources: <https://news.ycombinator.com/showhn.html>, <https://news.ycombinator.com/newsguidelines.html>

- The title begins "Show HN".
- It is for "something you've made that other people can play with".
- "The project must be something you've worked on personally and which you're around to discuss".
- Make it easy to try, with no signups.
- "New features and upgrades ... generally aren't substantive enough".
- "Please don't ask friends to upvote or comment".
- No uppercase for emphasis, no exclamation marks, no saying how great it is.
- "Please don't put generated text in HN posts. Write your text yourself".
- Comments: "Don't post generated text or AI-edited text."

### Timing (a preprint, not a rule)

Source: <https://arxiv.org/html/2511.04453v1>

- 138 launches of AI tools in 2024 and 2025.
- "The 12-17 UTC window performs best" (unadjusted).
- Show HN posts gained 119 fewer stars at 48 hours; p = 0.39, not significant.
- Observational, with a small sample. It does not prove that timing causes anything.

### Reddit: r/ClaudeAI and r/ClaudeCode

Rules **NOT verified**: the pages needed a login.

For both: read the sidebar rules logged in before posting: self-promotion, flair, disclosure.

### awesome-claude-code

Source: <https://github.com/hesreallyhim/awesome-claude-code> (CONTRIBUTING.md)

- The repository is at least 14 days old since its first commit, with active development, or has 100 stars.
- One resource at a time.
- Use the issue form in the web UI. "Do not open a PR". Not through the `gh` CLI.
- A human must create the submission.
- Description: 1 to 3 sentences, 10 to 500 characters, "Descriptive, not promotional. Don't address the reader". No emojis.

### Claude plugin directory

Sources: <https://code.claude.com/docs/en/plugins/publish.md>, <https://claude.com/docs/plugins/submit>

- Submit at <https://claude.ai/directory/manage>.
- Needs a paid claude.ai plan and GitHub connected.
- Anthropic checks each version.
- Run `claude plugin validate --strict` first.
- The portal form fields are **NOT verified** (Cloudflare challenge).

### dev.to

Sources: <https://dev.to/terms>, <https://dev.to/p/editor_guide>, <https://dev.to/code-of-conduct>

- A post must not be "designed primarily for the purposes of promotion".
- Disclose AI assistance (front matter `ai_disclosure_level`). The allowed values are **NOT verified**.
- Up to 4 tags.
- Set `canonical_url` if the article was published elsewhere first.

## Rules for every channel

- Do not ask anyone to upvote, star or comment.
- Quote a result only with its Herd version, model and run count, from [BENCHMARK.md](../../examples/supermarket-route/BENCHMARK.md) or [CHANGELOG.md](../../CHANGELOG.md).
- State the limits next to the result.
- Name no employer. The third use case is "a private research project on open map data" and nothing more.
- Answer questions yourself. Stay around on the day you post.
