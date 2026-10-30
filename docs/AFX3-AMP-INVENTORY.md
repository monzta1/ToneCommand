# FW33 amplifier inventory

The supported Axe-Fx III MK2 profile uses all 336 amplifier model names and
ordinals from the exact `33.00-beta.20261006` editor definitions. The factual
inventory ships in `devices/axefx3/data/fw33_amp_models.json`. It does not
require Axe-Edit at runtime, download amplifier algorithms, query arbitrary
model selectors, or assume that an FM9 model number is an Axe-Fx III number.
The models already exist on the hardware. Unknown firmware remains closed.

The request screen's collapsible AMP LIBRARY displays the inventory. The
configured AI receives all names as a strict schema enum and reference list.
It can choose any of them for Amp 1 channels A-D in the existing eight-scene
AMP/CAB build. Four stored amp configurations can be shared across eight
scenes; eight independent amp channels do not exist. Exact requested names
can be included in the request. Musical suitability is still a design choice,
not proof of the equipment on an original recording or an audible match.

REFRESH AMP MODELS verifies the connected firmware, reloads the bundled list
and compares it with the newest local product10 Axe-Edit metadata cache when
available. It does not need a running editor or fetch a live model enumeration
from the unit. Missing or unreadable caches are reported; other product
caches, unknown record layouts and partial files cannot silently become a
valid roster. Only amp labels leave the parser, never private IR tables.
New, renamed, renumbered or missing entries are shown separately and require
independent verification plus a TC update before becoming selectable. Refresh
does not change the planner enum, pending plan, draft, controller assignments,
preset or storage. It is safe to check during review without regenerating.

The expanded inventory does not enable generic raw model writes. Normal
review and SEND retain the deterministic build grammar, explicit mute
acknowledgement, pre-transition bypass and quiet level, unchanged output
attenuation, independent active-channel bulk model readback, and full-state
preservation checks. A matching model is retained without resetting its
voicing. A mismatch or unknown result stops without a write retry, rollback
or Store. Model ordinal zero uses its recorded discrete SET frame, not a
numeric zero-as-GET experiment. Other channels and blocks cannot change as
an undeclared side effect of a model reset.

This change does not expand Cab selection, Drive/post-EQ controls, arbitrary
grid layouts, new FW33 controller assignments, the one-scene serial test
mode, NAM selection, or supported firmware/hardware variants. The generic
registry model setter remains closed. Preset Store is a separate consent.

## Verification scope

The developer-only inventory probe requires the complete literal ordered
336-frame Axe-Edit recording and an independently checked quiet Amp 1/A
fixture on test preset 322. It has no API or planner action. Selection on A
for every model and representative normal A-D builds are separate evidence;
neither claims testing all 1,344 model/channel combinations or audio output.
Private captures and screenshots stay outside Git.

On 2026-10-16, Axe-Edit selected and independently displayed every one of the
336 exact names in ordinal order. Its passive outgoing recording contains
exactly those 336 selector frames, including a real change from model267 to
model0; no incoming traffic is claimed from that observer. TC subsequently
replayed all 336 on muted test322 and verified each model ordinal through
passive bulk readback, with complete preservation outside the active Amp/A
142-word reset region. No preset Store or shared-memory installation occurred.

A separate actual configured-provider request then used the registered plan,
review and SEND flow on322: 263 actions, models0/100/200/335 on A-D, and eight
native scene surveys checking all eight supported amp display values. After
releasing TC's MIDI connection, Axe-Edit independently confirmed all eight
scene names, channels, model names, main drive, Bass/Mid/Treble and Level.
The Bassguy Bright main drive is labelled Treble Gain in that editor, not its
separate Normal Gain. Explicit successful-test navigation returned to328/7
with complete original snapshot equality. Reference326 was not selected or
modified, and the test preset was not permanently saved.

The all-model release's complete simulator regression passes4,957 tests with16 skips. The
mandatory safety and all FX3 suites pass1,832 tests; subsequent focused
inventory/encoding tests pass35. Actual Chrome mocked workflow/library tests
pass, including all336 rendered names and normal consent. A built wheel also
imports the complete inventory and strict model enum in isolation from the
checkout. These checks are not an audio or safe-loudness measurement.

The subsequent refresh addition passes1,856 mandatory/FX3/encoding tests.
Chrome's mocked workflow verifies refresh success, new blocked names, failure
messages, XSS-safe rendering, and preservation of a draft and existing review.
A separate registered-API refresh on the connected unit reports all336 names
current and preserves complete before/after hardware snapshots on328/scene7.
That native test forbids every mutating device write, uses no AI and stores
nothing. Source metadata never becomes new selector authority.
