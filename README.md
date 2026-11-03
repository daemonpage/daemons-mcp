# daemons-mcp

**Connect Claude Code to Claude voice mode.** Give the Claude mobile app what it's missing: everything you've been doing in Claude Code.

My context and capabilities were all in Claude Code on my server, but the Claude app couldn't see any of it, so I couldn't think out loud with voice mode about what I was actually building. This connects the two.

It runs next to Claude Code and gives the Claude app (phone, web, desktop) a connector that can:

- **Find your context.** See your recent sessions, read them, and search everything you and Claude said, plus your memory files and `CLAUDE.md`.
- **Save tasks for later.** When an idea turns into something to build, Claude writes a markdown file called a bounty. Open Claude Code later, run `/bounties`, and an agent builds it.

It can't run code, start agents or message anyone.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

```bash
uvx --from git+https://github.com/daemonpage/daemons-mcp daemons start
```

It indexes your sessions and prints a connector URL. In the Claude app, go to **Settings > Connectors > Add custom connector** and paste it. There is no sign-in step. A new tunnel address can take a minute or two to start working.

Then ask Claude: *"what have I been working on?"*

To pick up bounties from Claude Code, install the command once and run `/bounties` in any session:

```bash
uvx --from git+https://github.com/daemonpage/daemons-mcp daemons install-skill
```

daemons has to stay running for the connector to work, so it suits a computer that stays on.

## Can I use Claude voice mode with Claude Code?

Not directly: voice mode in the Claude app can't see your Claude Code sessions. It can use connected tools, though, and [Anthropic says](https://support.claude.com/en/articles/11101966-using-voice-mode-on-claude-mobile-apps) they work the same way in voice mode as in text chat. daemons-mcp is a custom connector (a remote MCP server) that gives the app access to your sessions.

So you can ask out loud things like:

- "What was I working on yesterday in Claude Code?"
- "What did we decide about the payment retry?"
- "Save that as a task to build later."

## How it compares

| Tool | Best for | Difference |
|---|---|---|
| **daemons-mcp** | Thinking out loud with your Claude Code context, then saving tasks | One command, no sign-in step. Reads and saves tasks only, so it can't run anything on your computer |
| [claude-voice](https://github.com/roykollensvendsen/claude-voice) | Driving Claude Code sessions by voice from your phone | Can start sessions and send them tasks. Uses OAuth and Tailscale Funnel; GPL |
| [Remote Control](https://code.claude.com/docs/en/remote-control) | Steering a live session from the app | Official and built in, works on one session at a time rather than searching your history |
| [VoiceMode](https://github.com/mbailey/voicemode) | Talking to Claude Code at your computer | Adds speech inside Claude Code; doesn't connect to the Claude app's own voice mode |
| [claude-historian](https://github.com/Vvkmnn/claude-historian), [claudex](https://github.com/kunwar-shah/claudex) | Searching past sessions from inside Claude Code | Run locally for Claude Code rather than as a connector for the app |

If you want your phone to run code, use claude-voice. If you'd rather it couldn't, use this.

## Tools

| Tool | What it does |
|---|---|
| `get_current_context` | Recent sessions and open bounties. Claude calls this first. |
| `search_memory` | Keyword search across sessions and memory files |
| `list_sessions` | Sessions, newest first |
| `read_session` | The latest messages of one session |
| `read_memory_file` | One memory file in full |
| `write_bounty` | Save a task for an agent |
| `list_bounties` | Saved tasks by status |
| `read_bounty` | One saved task in full |
| `save_note` | Save a note that later searches can find |

## Bounties

Each bounty is a markdown file in `~/.daemon/mcp/bounties/`, and its folder is its status: `open`, `claimed`, `done` or `dropped`. Nothing starts automatically.

```bash
daemons bounty list
daemons bounty show <id>
daemons bounty claim <id>
daemons bounty log <id> "what happened"
daemons bounty done <id> "result"
daemons bounty drop <id>
```

## Security

Read this before connecting, because your transcripts may hold private things.

- **The URL is the password.** Anyone who has it can read your sessions and memory and write bounties and notes. To change it, delete `~/.daemon/mcp/secret` and restart.
- **What you share is sent to Claude.** Whatever the connector returns goes into your Claude app conversation, under your Claude account's data settings.
- **Secret removal is best effort.** Common API key formats and `KEY=value` pairs are removed from results, but a password in plain prose will get through. Rotate any key you pasted into a chat, and use `--only` to limit what is shared:

  ```bash
  daemons start --only my-project --only other-project
  ```

- **Tool output isn't indexed.** Only what you and Claude said is indexed, along with memory files and `CLAUDE.md`. Subagents and tool results are left out.
- **Treat bounties as untrusted.** Text in an old transcript could try to steer the Claude app into writing a bad bounty, for example if you once pasted in a malicious web page. Read a bounty before an agent with broad permissions builds it. The `/bounties` command tells agents to stop and ask before anything risky.
- **Local files stay local.** The server listens on `127.0.0.1` only and reads `~/.claude` without changing it. It writes only to `~/.daemon/mcp`, which also holds a plain-text search index of your sessions.

## A permanent URL

The quick tunnel's address changes on every restart, which means re-adding the connector. For a stable one, run `daemons start --no-tunnel` behind your own [named Cloudflare tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) or any reverse proxy pointing at `127.0.0.1:8765`.

## Development

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest
```

## Limits

- Search matches keywords, not meaning.
- Voice mode hasn't been tested end to end by this project yet; the connector has been tested in the Claude app's text chat.
- It reads Claude Code's transcript files, which aren't a documented format and could change.

More at [arthurcamara.com/daemons-mcp](https://arthurcamara.com/daemons-mcp/). Not affiliated with or endorsed by Anthropic. MIT licensed.
