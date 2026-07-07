# Wire EDM Post-Processor — SKD2 / EAPT

**Created by Arturo Rebolledo**

Reads a DXF profile, lets you set thread hole, lead-in/lead-out, entry/exit points interactively on a canvas, and generates ISO/G-code compatible with SKD2/SKDA wire EDM controllers. Includes contour detection, offset passes with per-pass E-parameters, path simulation, and manual drawing/editing tools (line, circle, arc, delete, custom path).

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
