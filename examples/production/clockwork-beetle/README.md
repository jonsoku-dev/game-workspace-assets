# Clockwork beetle — original local pixel character

A compact right-facing mechanical beetle: dark teal enamel plates, copper seams,
three pairs of articulated legs, one asymmetric pincer, mint eye and winding key.
64 × 48 transparent native pixels; common floor pivot `(29, 40)` from top left.
No antialiasing, resampled source art, vendor service, borrowed character, model,
font asset, or third-party visual input. `generate.py` is the complete original
integer-grid drawing source authored for this example; it uses existing Pillow.
The previews' small labels use Pillow's bundled default font and are not in sprites.

## Reproduce

From this directory, use the Python environment already supplying Pillow (the
installed pixel-asset launcher names it on its first line):

```sh
python3 generate.py
pixel-asset action-set --request actions.json --out /tmp/beetle-actions-NEW
python3 ../../../../studio/tools/scene.py validate --project .
```

The output directory for `action-set` must be new. `scene.json` is a normal studio
scene using the installed `pixel-action-set` producer. Production runs and SSOT
recording belong to the host, so no build or graph history is checked in here.
Every request input is local and included. To inspect, open `preview-1x.gif` at its
natural 128 × 80 canvas size and `contact-sheet-1x.png`; the 3× sheet uses nearest
neighbor scaling only. The CLI independently produces its own atlas and preview.

## Authored timing and semantics

| Action | Frames | Authored movement |
| --- | ---: | --- |
| idle | 4 | Exposed power chamber pulses; winding key turns one pixel. |
| walk | 6 | Alternating front/rear tripods, bent knees, lifted and planted feet. |
| run | 6 | Wider foot reach, quicker 65 ms poses, compressed shell stance. |
| attack | 5 | Brace, 170 ms open-claw telegraph, closed-jaw contact, two recovery poses. |
| jump | 5 | Crouch, launch, tucked legs at apex, unfold, compressed landing. |
| hurt | 3 | Backward shell recoil with folded legs and shocked open claw, settle, recover. |

Attack contact is zero-based frame 2 at 300 ms, around `(60, 26)` in the source
cell. This is an authoring cue, not an implemented hitbox. Motion is in-place;
the host owns travel, collision, state transitions and action interruption.
Jump includes local visual elevation and leg folding; the host must decide
whether to retain that offset or reconcile it with its physics trajectory.
No whole-sprite transform substitutes for the articulated gait or claw poses.

## Verification boundary

The generator asserts nonempty frames, all four transparent margins, and at least
three distinct poses per action. Local review used the native-size sheet, enlarged
sheet and browser playback of the actual 1× GIF. An early repeated gait hold was
replaced by explicit intermediate joint configurations. The apex was lowered one
pixel to preserve a transparent top margin. The installed CLI accepted an isolated
copy of the complete request and emitted `status: ready`; exact times stay in JSON
because GIF rounds to centiseconds. The asset package's 67 Python tests passed in
its prepared Pillow environment with `PYTHONPATH=assets/src`.

These are technical and local visual checks, not user art acceptance, continuous
frame-by-frame animation certification, gameplay tuning or real engine proof.
