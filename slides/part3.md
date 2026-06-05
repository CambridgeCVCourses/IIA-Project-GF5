# Part 3: Group Character Animation Project

## From mechanics to a finished scene

Use the FK and skinning pipeline to make a coherent 30-second (or longer)
human-avatar animation.

![Scene editor preview](assets/motion_scene_editor.png)

???
Open by making the shift explicit: Parts 1 and 2 were about understanding the
mechanics; Part 3 is about using those mechanics in a small production
workflow. Keep the tone practical. The target is a coherent final animation,
not a perfect professional animation system.

---

# Where We Are

- Part 1: skeleton hierarchy, local controls, world-space FK
- Part 2: rest pose, skinning weights, one-hot binding, LBS
- Part 3: motion clips, avatars, scene timing, camera, final evidence

???
Use this as the handoff from individual work to group work. The key message is
continuity: the Part 3 tools are not magic; they sit on top of the same
skeleton, pose, and skinning ideas students have just implemented.

---

# Part 3: Build A 30s+ Avatar Animation Scene

Work in groups of two to create a short animated scene featuring virtual human
characters.

- at least `30` seconds long
- coherent scene, not isolated test clips
- final video, saved scene files, and still frames for the report
- technical explanation of your workflow and limitations

???
Do not over-specify the creative brief. Students should have room to invent a
simple scene, but they should understand that the submitted work must be
explainable and inspectable.

---

# Scene Motion Editor

The GF5 scene motion editor is the main Part 3 composition tool.

Reference: [Scene Editor Manual](scene_editor.html)

![Scene editor preview](assets/motion_scene_editor.png)

???
Use this as the first concrete view of Part 3. Let students visually locate
the motion library, timeline, stage, avatar selector, and export controls
before naming each workflow step. Point students to the manual for the full
panel guide, file locations, shortcuts, export notes, and troubleshooting.

---

# What The Editor Lets You Do

- preview bundled motion presets
- arrange clips on character tracks
- edit `Path`, facing, timing, and camera
- save `.scene.json` drafts
- export screenshots or video evidence

???
Now name the main actions. The most important ones are adding a clip, changing
the path, changing facing, and saving the scene.

---

# Editor Demo

- `Motion Library`: choose preset or custom clips
- `Timeline`: arrange clips per character track
- `Stage`: edit root path and facing
- `Final avatar`: assign proxy, SMPL, or extracted avatar package
- `Export`: save draft evidence

???
Suggested setup before the session:

- `cd /home/mifs/sw2181/teaching/GF5/GF5`
- `python viewer/scene_web_server.py --port 8093`

Show a tiny scene: walk in, turn, wave, hold. Then save it and point out that
the `.scene.json` is part of the evidence trail.

---

# A Simple Way To Work

{{include: ../docs/part3.md#A Simple Way To Work}}

???
This is intentionally modest. Encourage students to make a rough working scene
first, save it, and improve it iteratively. That rhythm prevents them from
getting stuck waiting for a perfect avatar or perfect generated motion.

---

# Motion, Path, Facing, Camera

`Path` controls the character root trajectory.

- motion clip: local body pose over time
- `Path`: where the body root travels in the scene
- facing: which way the character looks while moving
- camera: how the audience reads the staged action

???
This framing matters. A walk cycle can be reused on different paths, and a
gesture clip can stay mostly in place. If students confuse path with pose, they
will often try to fix scene staging by searching for more clips.

---

# Motion Library

Preset clips are grouped by intended use.

- `Standing / Gesture`: mostly stay on one spot
- `Travel Loops`: repeated locomotion along a path
- `Travel Transitions`: starts, stops, and side steps
- `Turns`: changes in facing direction
- `Special Actions`: larger spot actions or original-travel beats

???
Encourage students to write down the clip names they use. The report should
make it possible to reconstruct what was selected, what was edited, and why.

---

# Good Scene Ingredients

- a small number of readable actions
- clear entrances, reactions, or final poses
- enough holds for the viewer to understand the action
- simple camera framing
- visible comparisons between draft and final

???
Simple usually wins here. A character walks in, turns, waves, waits, and exits
is a much better starting point than a crowded narrative that depends on
precise object interaction.

---

# Custom Avatars

The [GF5 UP2You demo](https://gf5-up2you.elliottwu.com) can reconstruct a
custom virtual character for final rendering.

- download the avatar package
- extract it under `libraries/avatars/`
- refresh the scene editor
- choose it from `Final avatar`
- compare proxy preview against final avatar render

![3D human reconstruction demo](assets/3d_human_recon_demo.png)

???
Frame avatars as a rendering and evidence extension, not as a prerequisite for
scene planning. Students can develop the scene on the proxy first, then test
whether a custom avatar preserves the action clearly enough.

---

# Avatar Package Layout

```text
libraries/avatars/alex/outputs/animation_lowres.obj
libraries/avatars/alex/outputs/animation_lowres_skinning_weights.npz
libraries/avatars/alex/outputs/smplx_mesh.obj
```

Extract each downloaded ZIP into its own named folder under `libraries/avatars/`.

???
Be very concrete here. The scene editor cannot load the ZIP as a ZIP; it needs
the extracted folder layout. The OBJ is the visible mesh, and the NPZ stores
how that mesh follows the course skeleton.

---

# Custom Avatar Example

{{video: assets/final_avatar_scene.mp4 | Example final render using a custom avatar. | autoplay | loop}}

???
Use this to set expectations. The purpose is not to promise artifact-free
rendering; it is to show the workflow idea: a scene can be planned with the
proxy and later rendered with a custom character.

---

# One Skeleton Connects The Pieces

GF5 uses the same 24-joint body skeleton across Part 3.

- proxy character
- preset motion clips
- imported or generated clips
- skinning weights
- custom avatar package

???
This is the technical bridge back to Parts 1 and 2. A motion clip only becomes
useful when the pose data, skeleton definition, and skinning weights agree
about the joint layout.

---

# SMPL-X To SMPL-24

Some reconstruction tools use SMPL-X internally.

- UP2You fits an SMPL-X-style body while reconstructing the avatar
- GF5 exports weights back to the course 24-joint skeleton
- the final avatar can follow the same clips as the `SMPL-24 Proxy`

???
Keep this high level. Students do not need to reimplement the mapping, but they
should be able to explain why the avatar can be driven by the same animation
skeleton as the proxy.

---

# Text-to-Motion Generation

HY-Motion-1.0 can generate short candidate motions from text prompts.

[Open the HY-Motion-1.0 demo](https://huggingface.co/spaces/tencent/HY-Motion-1.0)

![HY-Motion demo](assets/hy-motion-1.0.png)

???
Introduce this as an optional way to make extra atomic clips. Keep the emphasis
on short, inspectable motions. The online demo is the source students can try;
the GF5 editor is still where clips are composed into the final scene.

---

# Using Generated Motion Clips

- use one physical action per prompt
- keep the downloaded `.fbx` and `.txt` prompt together
- import the pair into the Motion Library
- treat generated clips as ingredients, not the whole scene

???
Treat generated motion as an optional source of atomic clips. The scene
composer remains GF5: generated clips should be short physical actions, not
entire long-scene story prompts.

---

# Prompt Atomic Actions

Good prompts describe one physical action.

- `A person walks forward and stops.`
- `A person turns left and waves.`
- `A person points forward with the right hand.`
- `A person performs a short dance step.`
- `A person stands still and raises both arms.`

???
This slide is about scope control. Multi-person interactions, exact props,
camera language, and full-scene prompts usually make a generated clip harder to
use in the editor.

---

# Import HY-Motion Clips

Keep the `.fbx` animation and matching `.txt` prompt together.

```text
wave_to_camera.fbx
wave_to_camera.txt
```

Use `Import HY-Motion` in the Motion Library panel and select both files.

The Scene Editor auto-finds motion clips in:

```text
libraries/motions/custom/
```

Imported clips are saved there. After import, refresh the Scene Editor page and
load the clip from `Custom:`.

???
This is the practical import rule. Same basename, same folder, select both.
Once imported, the clip is saved to `libraries/motions/custom/` and should
appear as a `Custom:` motion in the library.

---

# Hand Crafting Motion

You could also hand craft motions in the Asset Viewer.

Asset Viewer motions are saved to the same custom motion folder.

After saving a motion, refresh the Scene Editor page and load it from `Custom:`.

Motion clips from Parts 1 and 2 work too; move them into this folder if they
are somewhere else (recently changed from `libraries/motions/saved/` to
`libraries/motions/custom/`).

???
Make this feel like a creative option, not a legacy workaround. The point is
that saving a motion in the Asset Viewer puts it where the Scene Editor can
find it after a refresh. Older clips only need moving if they were saved
somewhere else.

---

# Week 3

## Build a proof of concept

- explore the bundled motion library
- make a rough scene on the `SMPL-24 Proxy`
- reconstruct or choose character assets
- save one or more `.scene.json` drafts
- bring a screenshot or clip to the help session

???
This is a planning slide for the first Part 3 week. A good Week 3 outcome is a
readable rough scene, even if the rendering is still basic and the custom
avatar has artifacts.

---

# Week 4

## Refine and submit

- improve timing, staging, and camera
- compare proxy preview against final avatar render
- collect final stills, clips, and artifact examples
- export a 30-second (or longer) final video
- write the final report

???
Make clear that Week 4 is not only rendering polish. It is also evidence
collection: students need comparisons and artifact discussion while they still
remember how each result was produced.

---

# Artifacts To Look For

- foot sliding
- scale or orientation mismatch
- skinning collapse near joints
- clothing or appearance loss
- awkward transitions between clips
- camera framing that hides the action

???
Normalize artifacts. The report is not weaker because it identifies problems;
it is stronger when the group can name visible limitations and connect them to
the workflow.

---

# Improve Rendering Quality

{{bullets: ../docs/part3.md#Improve Rendering Quality}}

???
Do not turn this into a mandatory checklist. The point is that students may
improve the final look through camera, lighting, background, timing, external
renderers, AI tools, or custom assets, as long as they can explain what they
used.

---

# Interim Report Feedback

Brief feedback on your interim reports has been uploaded to Moodle.

- you all did a very good job
- the tasks may have been a little too easy
- grades were spread a bit by report quality and the motion sequence created

???
Keep this encouraging: the overall standard was strong, but the marks still
needed to distinguish the clarity of the report and the quality of the motion
sequence.

---

# A Few Report Notes

- start with a brief summary of the report
- write equations using proper mathematical notation
- make FK robust to unsorted joint lists

???
For future reports, suggest a short opening summary even when it is not listed
as an explicit requirement. One short paragraph is enough: what problem the
report addresses, what method was used, what result was produced, and what the
main limitation or takeaway is. It helps the reader understand the aim, method,
and main result before the details.

For equations, encourage proper mathematical notation rather than prose-only
descriptions or code-like fragments. Define the variables, use matrices,
vectors, indices, and composition notation clearly, and keep implementation
details separate from the mathematical relationship being explained.

Use the next slide to explain the FK ordering issue.

---

# FK Ordering Pitfall

FK computes each joint world transform from its parent:

`W[j] = W[parent[j]] @ L[j]`

- this requires the parent's `W` to be ready first
- a plain loop only works if parents appear before children
- counterexample order: `wrist`, `elbow`, `shoulder`
- robust FK should sort parent-to-child, or recurse

???
Use a simple arm example. The shoulder is the parent of the elbow, and the
elbow is the parent of the wrist. The wrist's world transform depends on the
shoulder world transform, then the elbow world transform, then the wrist's own
local transform.

If the stored list is `wrist`, `elbow`, `shoulder`, and the code simply loops
through the list, it reaches the wrist before the elbow and shoulder world
transforms have been computed. That plain loop can therefore use a missing,
identity, old, or otherwise wrong parent transform.

Our course character happens to have its joints sorted parent-to-child, so this
bug may not show up on the given data. A robust FK implementation should not
depend on that convenience: either topologically sort the joints from the
parent array before looping, or compute recursively so each parent is computed
before its child.

---

# Part 3 Showcase

Tuesday 9 June 2026, 11am-1pm, LT6.

[Showcase notes](showcase.html)

- `9` groups
- `5` minutes presenting + `2` minutes Q&A per group
- `10` marks, so keep it light
- we will connect group laptops
- start with the animation, then tell the quick story
- share one trick, surprise, or useful failure

???
Emphasize that this is not a formal viva or a polished pitch deck. It should be
a short, technical, enjoyable show-and-tell from each group's own machine.
Tips, tricks, surprises, and useful failures are welcome.

---

# Presentation Order

| Order | Group | Order | Group |
| --- | --- | --- | --- |
| `1` | Matthew & Encheng | `6` | Elen & Sarah |
| `2` | Madeleine & Kavita | `7` | Yilia & Frank |
| `3` | Rohan & Sam | `8` | Tianze & Yunge |
| `4` | Serene & Aaron | `9` | Donna & Stan |
| `5` | Zohalb & Sean |  |  |

???
Use this as the confirmed showcase presentation order.

---

# Final Report

Deadline: Friday 12 June 2026, 4pm.

- [Final Report requirements](final_report.html)
- [Submit on Moodle](https://www.vle.cam.ac.uk/mod/assign/view.php?id=19560072)
- `8` pages max: up to `6` pages group work + up to `2` pages individual
- explain the scene and pipeline
- include final result plus a few useful figures
- discuss artifacts, limitations, and what you learned
- include the AI Use Statement

???
Keep this brief and high level. The canonical instructions live on the final
report page.

---

# Report Structure

- `Scene Plot`
- `Method`
- `Results And Evidence`
- `Artifacts, Limitations, And Reflection`
- `AI Use Statement`
- `Individual Contribution And Insights`

???
Point students to the canonical final report page after this. The report should
explain the pipeline and result; it should not become a diary of every command
they ran.

---

# AI Use In Part 3

- AI tools may support creative and production work
- generated motion, assets, editing, coding help, or writing support must be declared
- reports must still accurately explain your own workflow and evidence
- include an `AI Use Statement`

???
This is deliberately different from Parts 1 and 2. AI tools are allowed for
Part 3 production, but the declaration and explanation have to be honest and
specific.

---

# What Success Looks Like

- a readable 30-second (or longer) scene
- motion choices that match the intended action
- clear staging and camera
- a final render that improves on the draft
- honest discussion of artifacts and limitations
- reproducible evidence of the workflow

???
End on practical ambition. The best submissions will not necessarily use the
most tools; they will make coherent choices and explain them clearly.

---

# What To Bring To Help Sessions

{{bullets: ../docs/part3.md#What To Bring To Help Sessions}}

???
Ask for specific evidence. A saved scene and a short clip let staff diagnose
the problem much faster than a vague description.

---

# Calendar Reminder

{{schedule-calendar: project | updates}}

???
Use this as a closing schedule reset. Point out the Part 3 showcase slot and
the Friday 12 June submission deadline.

---

# Where To Go Next

- [Part 3 handout](part3.html)
- [Scene editor manual](scene_editor.html)
- [Showcase notes](showcase.html)
- [Final report](final_report.html)

???
Finish by sending students to the handout, manual, and report page. If time
allows, leave the scene editor open in the room and let students propose simple
scene ideas that can be built from the preset motion categories.
