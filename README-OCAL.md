# Ocal Record

A recording-focused customization of OBS Studio, cloned with all submodules.
The native Qt frontend has a charcoal/amber theme, Ocal Record branding and icon,
recording-first controls, a wide preview above a scene/source/audio workspace, and a right capture/transition
column. Outline SVG icons cover primary controls and workspace tools. The palette
is sampled from the supplied reference: #1E2329, #2A2F35, #3B4046, #F6A403,
#F5B402, and #FED255; red remains reserved for active recording.

## Build on Windows

This checkout's `windows-x64` preset targets **Visual Studio 2026**. Install its
Desktop development with C++ workload, the Windows SDK, and a CMake version that
supports the `Visual Studio 18 2026` generator. Git and network access are needed
for the pinned OBS dependencies. Follow the upstream build requirements linked
from `INSTALL` if configuring optional plugins.

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/ocal/build-windows.ps1
```

The script uses the upstream presets and creates `portable_mode.txt` in the run
directory. Launch `build_x64/rundir/RelWithDebInfo/bin/64bit/obs64.exe` after a
successful build. The executable and plugin target names deliberately retain
their upstream names for compatibility; the application title, About dialog,
Windows product metadata, default theme, and idle Windows tray icon are branded
Ocal Record.

Portable mode keeps this development build's settings separate from an installed
OBS. If using an existing settings folder, select **Settings → Appearance → Yami
→ Ocal Record** and **Docks → Reset Docks** to adopt the theme and layout. Saved
layouts and theme choices are otherwise respected. OBS's upstream updater and
repair UI are disabled to prevent replacing the custom build with stock OBS.

## UI verification

The interactive preview now supports scene creation, rename/removal, independent
source lists, and Screen (Display Capture), Particular Screen (Window Capture),
Video (Media Source), Text, Image, and Color sources rendered on the preview canvas.
Use the scene/source **+** buttons, double-click a scene to rename it, double-click
a source to edit its content or properties, or right-click for additional actions. The arrows
change layer order; checkboxes toggle visibility. Changes autosave to
`build-ocal-preview/workspace.json`, separately from OBS profiles. Video thumbnails
are generated with ffmpeg. Live screen capture provides real-time desktop preview at ~15 FPS,
and clicking **Start Recording** generates real 1080p30 H.264 `.mp4` video recordings saved directly
to `Videos/Ocal_Recordings/` using FFmpeg.

```powershell
python tools/ocal/test_all.py
python tools/ocal/preview.py --interactive
python tools/ocal/preview.py --test-workspace
```

```powershell
python -m pip install PySide6-Essentials Pillow
python tools/ocal/preview.py
```

This loads the actual Qt Designer forms, applies the Ocal theme overrides over a
small Fusion baseline, and checks the record button at 1440×900 and 1100×720.
Screenshots are written to `build-ocal-preview/`. The script also regenerates the
Windows icon from `frontend/forms/images/ocal-record.svg`.

The harness substitutes base Qt widgets for OBS-specific widgets and uses sample
source/mixer data. It is a UI preview, not a working capture application or a full
test of OBS's inherited Yami theme parser. Native compilation and actual recording
still need verification: this workstation has neither CMake on PATH nor an
installed Visual Studio C++ toolchain. No executable or installer has been built.

## Attribution and scope

Based on https://github.com/obsproject/obs-studio. OBS's authorship, source notices,
license, and contributor credits are retained. See `COPYING` and `AUTHORS`.
This is an independent customization, not an official OBS release. Plugin names,
service integrations, configuration formats, macOS packaging, Linux desktop
metadata, and upstream documentation retain their original identifiers.
