# Separated frontal traveller control

`relaxed-sprite.png` is an original 64×64 RGBA fixture authored for this repository with local Pillow drawing operations. The reproducible drawing is `draw_person` in `tests/test_rig_draft.py`. No external image, vendor code, generated model image, or downloaded art is incorporated.

The fixture depicts a frontal traveller with a contoured head, opaque eyes, narrow neck, connected shoulders, transparent gaps around hanging arms, two visibly separated legs, and boots. It is a structural test/control source, not evidence of user approval of any game art.

The source and request are provided under the MIT license in `LICENSE.txt`. The producer always writes `approved:false`. A synthetic test actor may toggle approval inside an isolated test only to prove compatibility; that does not authorize real production adoption.

Run from the assets repository with a fresh output path:

```sh
.venv/bin/pixel-asset rig-draft --request examples/production/rig-draft/request.json --out /tmp/traveller-rig-draft
```

Inspect `joint-preview.png`, every mask and `inspection.json`. Edit the proposed joints/masks where necessary. Only after an explicit actor reviews the master and draft should the actor set `approved:true` in the output's `rig-draft.request.json` and run `motion` on that file. No automatic approval is implemented.
