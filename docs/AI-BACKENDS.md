# Bring your own AI

ToneCommand does not ship a model or require any particular vendor. The
planner runs on whichever AI you already have, and every plan reports which
backend and model answered it.

The quickest route is the gear icon in the app: pick a service by name
(ChatGPT API, ChatGPT subscription, Gemini, Grok, DeepSeek, Kimi, a local
model, OpenRouter), and the address fills itself in, the model
box lists what your key can actually reach, and the panel says whether a key
is needed at all. Everything below is the same configuration by hand, plus
what each route honestly is.

## Backend order

Natural-language planning tries, in order of preference:

1. **An OpenAI-compatible endpoint**, if `PLANNER_BASE_URL` is set (see
   below). A configured endpoint wins: choosing one is deliberate, while a
   `claude` binary on `PATH` is an accident of the machine.
2. **The Claude Code CLI**, if installed and signed in (usage bills to your
   existing Claude subscription). The default when nothing is configured -
   a fresh checkout needs no key.
3. **The Claude API**: put `ANTHROPIC_API_KEY=sk-ant-...` in a `.env` file
   at the repo root.

A failed backend falls through to the next with its reason recorded.

Settings go in the environment or in `.env` at the repo root, the same file
the store whitelist uses:

| Variable | Default | Meaning |
|---|---|---|
| `PLANNER_BACKEND` | none | Pin one of `openai`, `cli`, `grok`, `api` and disable fallthrough. Required to reach the Grok CLI directly. |
| `PLANNER_BASE_URL` | none | OpenAI-compatible endpoint, including `/v1`. Setting it makes that backend first. |
| `PLANNER_MODEL` | `local` | Model for the OpenAI-compatible path. |
| `PLANNER_API_KEY` | none | Only if your endpoint wants one. Often nothing is needed. |
| `PLANNER_MAX_TOKENS` | `8192` | Reply cap on the OpenAI-compatible path. Reasoning models need headroom. |
| `PLANNER_TIMEOUT` | `180` | Seconds allowed per backend attempt. |
| `GROK_CLI_MODEL` | none | Model passed to the `grok` CLI. Unset uses its own default. |

## Using ChatGPT

Open the gear, choose **ChatGPT, Gemini, or another service you choose**, and
click the **ChatGPT API** chip. That fills in the address. Paste a key from
platform.openai.com and save, and the model box fills itself in with one your
key can actually reach, picked from the service's own list. Change it from the
dropdown if you want a different one.

A key is genuinely required on this route, and so is a model: with the box
blank the planner sends `local`, which a hosted service answers with a 404 for
a model nobody asked for.

Note that an OpenAI API key is a separate, pay-per-request account from a
ChatGPT Plus subscription.

## Using Gemini

Same panel, click the **Gemini** chip. The address it fills is Google's
ChatGPT-compatible endpoint for the Gemini API. Get a key from Google AI
Studio (aistudio.google.com), which takes about a minute, and its free tier
covers tone planning. Save the key and pick a model from the list that
appears.

## Using Grok, DeepSeek or Kimi by key

Each has a chip that fills in its address; each needs its own per-request API
key (console.x.ai, platform.deepseek.com, platform.moonshot.ai). If you
already pay for Grok itself, the **Grok CLI** backend in the dropdown runs on
that subscription instead: install xAI's Grok CLI as its own documentation
directs (`curl -fsSL https://x.ai/cli/install.sh | bash` at the time of
writing), sign in, then set `PLANNER_BACKEND=grok`. Its replies are
constrained to the planner's JSON schema, which the Claude CLI path cannot
do. Verified against grok 1.0.5.

## Using the ChatGPT subscription you already pay for

Choose **ChatGPT subscription** and click **SHOW ME HOW**. Each
step has a **DO IT FOR ME** button; the only one you have to do yourself is
signing in to your own ChatGPT account, which opens in your browser. The
terminal command for every step is still there under *or run it yourself*, for
anyone who would rather see what runs on their machine, or who is not on
Homebrew.

It checks your machine after every step and will not advance on your say-so,
so a step that silently failed is caught where it happened rather than at the
next prompt.

It installs [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI), a
separate MIT-licensed service (`brew install cliproxyapi`), signs it into your
ChatGPT account over the normal OAuth flow, replaces the placeholder passwords
it ships with, and starts it as a background service. The app never runs any of
that itself: it shows you the command and verifies the result. The password is
derived from your machine and filled into the panel for you.

Proven end to end on a ChatGPT Plus account: a plan came back in 8.5s through
`gpt-5.5` with three valid actions and no validation errors.

Two things worth knowing. OpenAI sells Codex for use through their own
clients, and routing it into another app is not something they bless, so it
could change without notice. And the same setup also covers Gemini, Grok and
Kimi on their own logins.

## A router, or a local model

Anything else goes through
[CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) run by hand. It is
a separate MIT-licensed service, not bundled here and not a Python dependency.
Log it into whichever upstream you want (Claude Code, Codex, Grok, Gemini,
Kimi all authenticate over their own OAuth), then point this tool at it:

```
PLANNER_BASE_URL=http://127.0.0.1:8317/v1
```

The same setting reaches a local model instead: LM Studio defaults to
`http://127.0.0.1:1234/v1`, Ollama to `http://127.0.0.1:11434/v1`. An API key
is usually unnecessary: an OAuth router authenticates upstream on its own.

## Two honest caveats

Only the Claude API and Grok CLI paths *constrain* output to the plan schema;
the Claude CLI and OpenAI-compatible paths ask for JSON and are believed,
which is why validation against the device reference is load-bearing rather
than a safety net. And a weaker model proposes worse tones. It cannot hurt the
rig, since nothing transmits without your confirmation, but it wastes your
time.
