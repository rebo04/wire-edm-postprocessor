# Wire EDM Post-Processor — SKD2 / EAPT

**Created by Arturo Rebolledo**

Reads a DXF profile, lets you set thread hole, lead-in/lead-out, entry/exit points interactively on a canvas, and generates ISO/G-code compatible with SKD2/SKDA wire EDM controllers. Includes contour detection, offset passes with per-pass E-parameters, path simulation, and manual drawing/editing tools (line, circle, arc, delete, custom path, measure).

### Key features

- **Material library (Seguro / Rápido)** — built-in starting E-params for **Carburo-Tungsteno, Aluminio, Acero dulce, Acero tratado, D2, A2, S7** with 0.18mm molybdenum wire, auto-scaled to the material thickness (longer Pul_On, more flushing off-time and +V for thick plates; linear speed drops inversely with thickness). Pick the material, the Perfil (**Seguro** = conservative, protects wire and finish; **Rápido** = faster roughing), enter the espesor and hit **⚙ Aplicar**. `SKD11` is accepted as an alias of `D2`. *These are starting values — always validate against your machine's manual.*
- **Puente / tab cutting (ping-pong skims)** — set **Puente mm** > 0 and the cut stops that many mm before closing the contour, so the piece never falls on the wire. With 2+ passes the skims alternate direction: pass 2 returns in reverse along the same path (compensation auto-flipped G41↔G42), pass 3 goes forward again. Ends with `M00` so you can break the tab manually. In the ⧉ TODO multi-contour program the tab applies only to the outer profile — interior holes still cut full.
- **Kerf preview + gouge check** — draws the *real* compensated wire path (G41/G42 × offset H1) as an amber dashed line, and flags in red any inside radius smaller than the offset — the exact geometry that makes the controller alarm or gouge the part.
- **Material presets** — save proven E-params/offsets/passes per material + thickness (`💾 PRESETS` in the sidebar) and reload them in one click. Stored in `~/.wedm_presets.json`.
- **Multi-contour program (⧉ TODO)** — generates ONE ISO that cuts every contour in the plate: interior openings first, outer profile last, with `M00` re-thread stops between contours.
- **Cut time estimate** — shows estimated machine time in the status bar and as a comment in the ISO header, based on the editable `Vel mm/min` cutting speed (skim passes assumed ~3× faster).
- **📐 Medir tool** — click two points (snaps to endpoints) to measure distance, ΔX/ΔY and angle on the canvas.

### Rolling back

Every version stays available on the [Releases](../../releases) page — if a new version misbehaves, just download the previous one.

---

## Option A — Download & Run (no Python needed)

Go to the [**Releases**](../../releases/latest) page and download:

| Platform | File | How to open |
|----------|------|-------------|
| **Windows** | `WireEDM_PostProcessor.exe` | Double-click |
| **macOS** | `WireEDM_PostProcessor_macOS.zip` | Unzip → **right-click** the `.app` → **Open** *(first time only, to bypass Gatekeeper)* |

---

## Option B — Run from source (Python)

### First time setup

**macOS** — double-click `install_mac.sh`
> If macOS blocks it: right-click → Open → Open

**Windows** — double-click `install_windows.bat`

Both scripts automatically install Python and all packages if missing, then launch the app.

### After setup (daily use)

| Platform | Launch |
|----------|--------|
| macOS | double-click `run_mac.command` |
| Windows | double-click `run_windows.bat` |

Or from terminal:
```bash
python app.py
```

You can also open a DXF directly from the command line:
```bash
python app.py path/to/part.dxf
```

---

## How it works

1. Click **📂 Abrir DXF…** and select a `.dxf` file (optionally filter by layer)
2. Pick **Modo** (Core = punch, Cavity = die), **Cutin** style, compensation, and number of passes
3. Set **Hilo** (thread hole), **Entrada**/**Salida**, and **Lead-in**/**Lead-out** points on the canvas — by clicking or by angle + distance
4. Fill in material, thickness, wire diameter, offsets (H) and E-params per pass
5. Click **▶ Generar** to build the ISO code, **▶ Simular** to preview the toolpath, and **💾 Guardar .ISO** to export

### Drawing tools

`/ Línea`, `○ Círculo`, `( Arco`, `✕ Borrar`, `↩ Undo` let you sketch or fix geometry directly on canvas. `⤷ Path` lets you manually pick the segment order/direction for the cut instead of relying on automatic contour detection.

---

## Security & privacy

Wire EDM Post-Processor works **100% offline** — it never touches the network for its normal operation.

- The only network call in the source is a one-time, local `pip install ezdxf` if that dependency isn't already installed on first run — after that, the app runs fully local.
- No telemetry, no analytics, no auto-update check.
- **Local-only file I/O.** It only reads the `.dxf` you pick and writes the `.ISO` file you choose to save.
- **Verify it yourself** — the entire source is `app.py`; a quick `grep -i "requests\|urllib\|socket\|http\."` over it shows zero matches.

The only outbound connection in this whole *project* is GitHub's own infrastructure building the `.exe`/`.app` releases via Actions when a new version is tagged.

---

## Requirements (if running from source)

- Python 3.9+ (with Tk support — the standard python.org / Homebrew `python-tk` installers include it)
- `ezdxf`

```bash
pip install ezdxf
```

---

## Build executables locally

```bash
pip install pyinstaller ezdxf

# macOS
pyinstaller --windowed --name "WireEDM_PostProcessor" app.py

# Windows
pyinstaller --onefile --windowed --name "WireEDM_PostProcessor" app.py
```
