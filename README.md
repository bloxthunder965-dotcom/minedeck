# MineDeck

A Minecraft: Java Edition launcher UI built with Python and Flet 1.1.2.

MineDeck installs real Minecraft versions, resolves Fabric/Quilt/Forge/NeoForge
loaders, browses Modrinth content, signs in with Microsoft or a local profile,
and manages isolated instances. The desktop build launches Java directly. The
Android build is a Flet UI: Minecraft's JVM/OpenGL runtime and injection of
touch input into another Android app require a native host and are not provided
by Flet alone (see **Known limits**).

## Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install flet==1.1.2
python app.py
```

The app starts a web server on `0.0.0.0:8550` and opens a browser. Set
`MINEDECK_PORT` to change the port (do not use `PORT`; it is reserved by the
OpenCode host in this workspace).

Data is stored under the first available location:

1. `$MINEDECK_HOME`
2. `$FLET_APP_STORAGE_DATA` on Android
3. `~/.minedeck`

Game metadata, libraries and assets live in `<data>/game`. Each instance has
its own `mods/`, `resourcepacks/`, `shaderpacks/`, `saves/` and `logs/`.

## Accounts

- **Microsoft**: create an Azure app registration (public client, device-code
  flow), enable "Allow public client flows", and add the Minecraft scope.
  Paste the application (client) ID into Settings. No credentials are bundled.
- **Local profile**: generates a Java-compatible offline UUID
  (`MD5("OfflinePlayer:<name>")`), token `"0"`, and `legacy` user type. Use it
  for worlds you already own, LAN play, and testing. Online servers with
  authentication enabled will reject it.

## Desktop launch

Minecraft needs a Java runtime. MineDeck detects `java` on `PATH`; set an
explicit executable in Settings if needed. The launcher writes the standard
version/asset/library layout and starts Java with the resolved classpath and
native libraries. Java 21 is required for recent Minecraft versions.

## Android build

### GitHub Actions (no local Android SDK)

Push this project as a GitHub repository. The workflow in
`.github/workflows/build-apk.yml` builds the APK automatically on every push to
`main`/`master`, or manually from **Actions → Build Android APK → Run workflow**.
Download the APK from the run's **Artifacts** section.

The project root must be this `minedeck` directory (the folder containing
`app.py` and `pyproject.toml`).

### Local build

Install Flutter and the Android SDK, then:

```bash
pip install flet==1.1.2
flet build apk
```

The APK is written to `build/apk/`.

Flet packages the Python UI and assets; it does not package a JVM, OpenGL
context, or an input-injection service. A production Android release needs a
native companion host that:

1. starts the JVM and Minecraft with the generated arguments, and
2. exposes the exported control layout to an Android input source
   (Accessibility Service, rooted `uinput`, or an embedded host view).

## Touch controls

Settings → Touch controls opens a layout designer: draggable joystick and
buttons, presets, size/opacity/sensitivity controls, and JSON export. The JSON
contains normalized coordinates plus Android keycodes and mouse bindings. It is
a real layout contract for a native host; the Flet app itself cannot inject
events into another app.

## Verified in this workspace

- Real Mojang manifest and version metadata fetches.
- Fabric loader resolution; Forge/NeoForge installer metadata parsing.
- Modrinth search results.
- SHA1-verified download and resumed HTTP downloads.
- Offline UUID generation and control-layout export.
- All page builders at phone and desktop sizes with empty and populated data.

Not verified here: Minecraft launch (no Java runtime), APK build (no Android
SDK/Gradle), and native touch input injection (requires a native Android host).
