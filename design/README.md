# SABC glass interface

The homepage sculpture is an original Blender model: project documents and evidence
feed an eight-dimension assessment, with neutral S/A/B/C keys. These are illustrative
keys, not a selected rating or project data.

- Editable source: `sabc-dossier.blend`
- Runtime asset: `../public/models/sabc-dossier.glb`
- Static fallback rendered from the same source: `../public/models/sabc-dossier.png`
- Rebuild on this Mac: `/Applications/Blender.app/Contents/MacOS/Blender --background --python scripts/build_dossier.py`

The script uses the system Arial Unicode font and converts lettering to meshes.
No font binary is included. Camera and lighting remain in the Blender source;
only geometry and materials are exported to GLB. No external textures or paid
assets are required. Three.js and its GLTFLoader are MIT licensed.

`app/dossier-scene.tsx` loads Three.js and the GLB near the viewport, uses a capped
pixel ratio, and releases GPU resources when the homepage unmounts. The model has a
fixed pose with no automatic motion or pointer rotation. It renders on load,
resize, and return to view, without a continuous animation loop.
WebGL/model failures retain the rendered poster and do not block the workbench.

`app/glass.css` applies the shared dark glass palette to existing components.
The glass appearance uses translucent gradients, backdrop blur, and inset edge
highlights, inspired by the supplied liquid-glass reference. Text is never blurred.
Browser-dependent displacement is not required. Print uses white paper; reduced
transparency and browsers without backdrop filtering receive opaque surfaces.
