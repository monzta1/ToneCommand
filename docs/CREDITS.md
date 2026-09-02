# Credits and prior work

This project would not exist without the Fractal community's protocol work.
The heavy lifting of reverse-engineering the FM9-Edit editor protocol was
done by others; this project builds on it, verifies it against hardware,
and contributes corrections back
([PROTOCOL-CONTRIBUTIONS.md](PROTOCOL-CONTRIBUTIONS.md)).

- **[mcp-midi-control](https://github.com/TheAndrewStaker/mcp-midi-control)**
  by **Stephen Staker** (TheAndrewStaker), Apache-2.0. The foundation. Its
  `SYSEX-MAP.md` is the best public documentation of the gen-3 Fractal
  editor protocol, byte-verified from hardware captures and binary mining.
  This project's `fm9/protocol.py` is a Python port of its TypeScript
  codec, and `config/fm9_catalog.json` is its FM9 parameter catalog,
  vendored verbatim. Roster data therein derives in part from
  **fractal-syx-codec** by Andrew Mercurio (Apache-2.0), and the grid-read
  cell layout was originally contributed by the **ai-tone-assistant**
  project (MIT).
- **[forgefx-midi](https://github.com/sKuhLight/forgefx-midi)** and
  **[ForgeFX](https://github.com/sKuhLight/ForgeFX)** by **sKuhLight**
  (Apache-2.0 and MIT respectively). Source of the FM9 modifier model:
  slot addressing, the binary-mined field map, and the bind sequence that
  makes expression-pedal assignments possible over MIDI. Re-implemented in
  Python here; ForgeFX was consulted, no code copied.
- **Fractal Audio Systems** publishes the official third-party MIDI spec
  ("Axe-Fx III MIDI for Third-Party Devices", Rev 1.4) that covers the
  documented command set: scenes, bypass, channels, names, tempo, and the
  effect ID table.

## Contributors

Everything above is prior art this project builds on. These people built the
project itself.

- **[@bschmalz81401](https://github.com/bschmalz81401)** (Brian Schmalz).
  Thirteen merged pull requests and the largest single body of work here after
  the maintainer's. The "bring your own AI" backends, so the planner runs on
  Grok, any OpenAI-compatible endpoint, or a model on your own laptop.
  Building a preset from scratch into an empty slot. Selective cable removal,
  decoded and hardware verified, and the block splice it makes possible, which
  is what lets a block go into a chain with no room in it. The cab roster
  mapped to the real cabinets. He tests his own changes against real hardware,
  files the bugs he finds in his own pull requests out loud, and on one
  occasion closed a PR of his own in favour of a fix he thought was worse than
  it was, then caught the maintainer merging the wrong one anyway. That last
  part is rarer than it sounds and it is why this project's simulator is
  honest about the hardware.
- **[@Triumph1701](https://github.com/Triumph1701)**. Designed the planner
  backend fall-through contract (#7): how the app degrades cleanly across
  wildly different AI backends, which of them can constrain output and which
  cannot, and why validation stays load-bearing regardless. Implemented as
  specified.

Full license reproductions and file-level provenance:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
