# Sazed — Sub-project 2a: one-shot PC skills

Date: 2026-10-15
Status: Draft, awaiting review.
Builds on: [sub-project 1](./2026-10-14-sazed-core-design.md) (merged on `main`). Everything
there still holds unless this document says otherwise.

## 1. Context and intent

**What the user asked for** (brainstorm, 2026-10-15):
- Roadmap item 2, "PC skills (apps, windows, media, files)". The user picked all four areas
  (media playback, windows, files and folders, system), plus three suggestions: websites and web
  search, Store/UWP apps, system status.
- Seven areas are too many for one spec. Split, as the user chose:
  - **2a (this spec):** one-shot commands that need no new kind of reference: media, system,
    web, status, Store apps.
  - **2b (later, its own brainstorm):** windows and files, which need new slot kinds (running
    windows, file search, ambiguity among files).
- Power actions always confirm; lock runs directly. Default web search: Google. Screenshot: both
  forms, chosen by phrase. Windows access: native APIs in-process (approach A).
- Sub-project 1's deferred minors are fixed here, first.

**Assumption, not stated by the user:** success means doing, by typed pt-BR, the everyday PC
tasks the user would otherwise reach for the mouse to do. Voice remains sub-project 4.

**Hardware facts checked on 2026-10-15:** desktop, no battery; two monitors, one of which
reports WMI brightness control; the Start menu lists 238 apps, including the Store apps
WhatsApp, Calculator and Notepad.

### 1.1 Success criteria

1. In the terminal, pt-BR phrases control media playback, lock/power the PC (with
   confirmation), take screenshots, open Settings pages, set brightness where supported, open
   websites, search the web, answer memory/CPU/disk status, and open/close Store apps.
2. The NLU fixture, extended with the new intents, meets the existing bar (accuracy ≥ 0.90,
   false-execute ≤ 0.02).
3. A power action never runs without a confirmation, at any score, after any learning.
4. Sub-project 1's six deferred minors are fixed, each with a test that failed first.

### 1.2 Out of scope

Windows and files (2b); battery; per-app volume; closing browser tabs; voice; the SLM; the
tokenizer memory fix (measured, not fixed).

## 2. Stack additions

- `winrt-Windows.Media.Control`, `winrt-Windows.Foundation`,
  `winrt-Windows.Foundation.Collections` (media sessions), `winrt-Windows.Management.Deployment`
  (Store package install folders). Versions pinned in `uv.lock`; Python 3.12 wheels confirmed
  during setup.
- `Pillow` (multi-monitor screenshot via `ImageGrab.grab(all_screens=True)`).
- Already present: `pywin32` (WMI brightness, `shell:AppsFolder`), `psutil` (status, processes).

The idle-memory increase is measured and recorded (§9).

## 3. Intents

Intent ids are pt-BR, as in sub-project 1. Seeds follow sub-project 1's rule: opposing intents
share objects so the verb decides (e5 weighs the object over the verb).

| Skill | Intent | Example | Slots | Confirms | Repeatable |
|---|---|---|---|---|---|
| media | `midia_tocar_pausar` | "pausa a música", "continua" | — | no | no |
| media | `midia_proxima` | "próxima música" | — | no | yes |
| media | `midia_anterior` | "volta a música" | — | no | yes |
| media | `midia_tocando` | "o que está tocando?" | — | no | no |
| system | `pc_bloquear` | "bloqueia o computador" | — | no | no |
| system | `pc_desligar`, `pc_reiniciar`, `pc_suspender`, `pc_sair_conta` | "desliga o pc" | — | **always** | no |
| system | `print_tela` | "tira um print" | — | no | no |
| system | `recortar_tela` | "recorta a tela" | — | no | no |
| system | `abrir_configuracao` | "abre as configurações de bluetooth" | `pagina` (optional; absent → Settings home) | no | no |
| system | `brilho_definir` | "brilho em 40" | `percent` (required) | no | no |
| system | `brilho_aumentar`, `brilho_diminuir` | "aumenta o brilho" | `percent` (step), `alvo` (level) | no | yes |
| web | `pesquisar` | "pesquisa receitas de bolo", "pesquisa lofi no youtube" | `consulta` (required), `site` (optional) | no | no |
| status | `status_memoria`, `status_cpu`, `status_disco` | "quanta memória está livre?" | — | no | no |
| apps (changed) | `abrir_app`, `fechar_app` | "abre o whatsapp", "abre o youtube" | `app` | as today | no |

**Sites are app catalog entries, not a separate intent.** "abre o youtube" and "abre o chrome"
differ only in an object the embedder has not seen, so `abrir_site` vs `abrir_app` would tie
constantly. Instead the catalog behind the `app` slot holds .lnk apps, Store apps and sites;
`abrir_app` opens whichever the slot resolves to. Learning and aliases work for sites unchanged.
- Name collision (a site and an installed app score equally): the installed app wins. Sites
  that need disambiguation carry their own name ("whatsapp web").
- `fechar_app` on a site returns `CannotCloseSite`.

**Brightness** mirrors volume exactly: `percent` is a step, `alvo` the level to end at,
`alvo` wins (sub-project 1's `dca1af4`).

### 3.1 Settings pages (`pagina` slot)

A fixed pt-BR list, matched like apps (fuzzy, accents stripped, aliases learnable). Each entry
maps to an `ms-settings:` URI; the `-m windows` test opens one, and the pure test asserts every
URI has the `ms-settings:` scheme.

| pt-BR names | URI |
|---|---|
| bluetooth, dispositivos | `ms-settings:bluetooth` |
| wi-fi, wifi, rede, internet | `ms-settings:network-wifi` |
| som, áudio | `ms-settings:sound` |
| tela, vídeo, monitor, resolução | `ms-settings:display` |
| atualizações, windows update | `ms-settings:windowsupdate` |
| aplicativos, programas | `ms-settings:appsfeatures` |
| armazenamento, disco | `ms-settings:storagesense` |
| energia, bateria, suspensão | `ms-settings:powersleep` |
| notificações | `ms-settings:notifications` |
| plano de fundo, papel de parede, personalização | `ms-settings:personalization-background` |
| privacidade | `ms-settings:privacy` |
| mouse | `ms-settings:mousetouchpad` |
| teclado, digitação | `ms-settings:typing` |
| impressoras | `ms-settings:printers` |
| data e hora, relógio | `ms-settings:dateandtime` |
| contas, minha conta | `ms-settings:yourinfo` |
| sobre, sistema, informações do sistema | `ms-settings:about` |

### 3.2 Behaviour rules

- **Power actions** (`pc_desligar`, `pc_reiniciar`, `pc_suspender`, `pc_sair_conta`) declare
  `requires_confirmation = always`. They confirm at score 1.0 and after any learning.
- **Power actions are never learned.** A confirmed "sim" executes but stores no example and
  offers no learning. New `IntentSpec.learnable: bool = True`; power intents set `False`.
  The runtime checks it before every learning signal in §5.1 of sub-project 1.
- **Repeat is opt-in.** New `IntentSpec.repeatable: bool = False`. "de novo"/"mais" repeat only
  a repeatable last intent; otherwise `NothingToRepeat`. Repeatable in sub-project 1's skills:
  `volume_aumentar`, `volume_diminuir`. This fixes deferred minor #8 (a bare "mais" opening a
  second Chrome). A bare "mais" with nothing repeatable is never ranked as an intent.
- **Power acknowledges before acting.** The skill returns `PowerAction(kind)` and the adapter
  call is made after the response is rendered, through a deferred action the runtime runs last
  (so the user sees "Desligando…" before the PC goes down). Lock runs the same way.
- **Screenshot file name** is built by the skill from `ctx.now`:
  `Captura AAAA-MM-DD HH-MM-SS.png` in the user's `Imagens\Capturas de tela` folder (resolved by
  the adapter via the known-folder API, not a hardcoded path). An existing name gets a ` (2)`
  suffix; never overwritten.
- **Search URLs** are built by a pure function: the query is URL-encoded (`quote_plus`) and
  substituted for `{q}`. The query is never passed to a shell.

## 4. Ports and adapters

Ports live next to the skill that uses them; adapters in `adapters/windows`. Skills stay pure.

| Port | Methods | Adapter |
|---|---|---|
| `MediaControl` | `toggle() -> bool`, `next() -> bool`, `previous() -> bool`, `now_playing() -> NowPlayingInfo \| None` (`False`/`None` = no session) | WinRT `GlobalSystemMediaTransportControlsSessionManager`; async calls run to completion inside the adapter |
| `Power` | `lock()`, `shutdown()`, `restart()`, `sleep()`, `sign_out()` | `LockWorkStation`, `SetSuspendState`, `shutdown.exe /s /t 0`, `/r /t 0`, `/l`. Command construction is a pure function, tested |
| `Screen` | `capture(file_name) -> str` (full path), `open_snip()` | Pillow `ImageGrab.grab(all_screens=True)`; `ms-screenclip:` |
| `Brightness` | `get() -> int \| None`, `set(percent) -> bool` (`None`/`False` = unsupported) | WMI `WmiMonitorBrightness` / `WmiMonitorBrightnessMethods` via pywin32 |
| `UriOpener` | `open(uri)` | `os.startfile`. Used for sites, searches, `ms-settings:`, `ms-screenclip:`, Store app ids |
| `SystemStatus` | `memory() -> (free_bytes, total_bytes)`, `cpu_percent() -> float`, `disks() -> list[(mount, free, total)]` | `psutil` (`cpu_percent(interval=0.3)`; fixed disks only) |
| `AppCatalog` (changed) | `entries()` now also yields Store apps and sites | `.lnk` scan + `shell:AppsFolder` + config sites |
| `AppLauncher` (changed) | `launch`/`instances`/`close` handle all three kinds | see §4.1 |

### 4.1 App entries

`AppEntry` gains `kind: Literal["lnk", "store", "site"]`.
- `lnk`: unchanged.
- `store`: `target` = AppUserModelID. Launch opens `shell:AppsFolder\<AUMID>`. Close/instances:
  the AUMID's package family → install folder (`PackageManager`), then root processes whose
  executable lives under that folder (the folder matching added for Squirrel launchers in
  sub-project 1). Resolved once per catalog load.
- `site`: `target` = URL. Launch opens it; `instances` = 0; close → skill returns
  `CannotCloseSite`.
- Dedupe by normalised name: `lnk` beats `store` beats `site`. Uninstaller shortcuts stay
  filtered, now including "Desinstalação …" / "Desinstalar …" (deferred minor).

## 5. Configuration

```toml
[sites]                    # merged over the built-in defaults; same name overrides
youtube = "https://www.youtube.com"

[search]
default = "google"         # must name an engine below

[search.engines]           # merged over built-ins; {q} = the URL-encoded query
youtube = "https://www.youtube.com/results?search_query={q}"
```

Built-in sites: youtube, gmail, github, whatsapp web, netflix, google drive, google maps,
wikipédia. Built-in engines: google, youtube, wikipédia.

Validation at startup, all messages pt-BR, schema-driven test (sub-project 1's pattern):
- every site URL and engine template is `http` or `https` (no `file:`, no bare paths: a typo
  must never make Sazed run a local file);
- every engine template contains `{q}` exactly once;
- `search.default` names a known engine;
- site names are non-empty after normalisation.

## 6. Slots

| Slot | Extractor | Notes |
|---|---|---|
| `pagina` | fuzzy over §3.1 names (same scoring as `app`) | absent → Settings home |
| `consulta` | the text after "pesquisa/pesquise/procura/busca/pesquisar (por/sobre)", minus a trailing "no/na <engine name>" | empty → `None` → asks "O que devo pesquisar?" |
| `site` (for `pesquisar`) | the trailing "no/na <engine>" phrase, matched against engine names | absent → `search.default` |
| `app` | unchanged matching, over the larger catalog | — |

## 7. Outcomes and persona

New `Outcome` values, each with pt-BR templates (the persona test demands them automatically):
`MediaToggled`, `MediaSkipped(direction)`, `NoMediaSession`, `NowPlaying(title, artist)`,
`NothingPlaying`, `PowerAction(kind)`, `ScreenshotSaved(file_name)`, `SnipOpened`,
`SettingsOpened(page)`, `BrightnessSet(percent)`, `BrightnessUnsupported`, `SiteOpened(name)`,
`SearchOpened(query, engine)`, `CannotCloseSite(name)`, `MemoryStatus(free, total)`,
`CpuStatus(percent)`, `DiskStatus(disks)`, `NothingToRepeat`.

- Numbers are rendered in pt-BR by a pure formatter (`5,2 GB`, `37%`), tested with values that
  differ between locales (1234.5 → `1.234,5`).
- `NowPlaying` with an empty artist omits ", de …".
- Unexpected adapter exceptions become `ActionFailed(describe(slots))` and are logged
  (sub-project 1 path, unchanged).

## 8. Deferred minors from sub-project 1 (fixed first)

1. **#5:** the CORRECTED reaction can land on a later non-executing episode. Fix: attach it to
   the episode of the executed command being corrected.
2. **#6:** a coppermind write failure after a successful action is reported as total failure.
   Fix: the action's outcome is reported; the learning failure is logged and Sazed says it could
   not remember it.
3. **#7:** an explicit step of 0 becomes 10, and an out-of-range step silently uses 10. Fix:
   absent → default, 0 → no change acknowledged, out of range → ask.
4. **#8:** fixed by opt-in repeat (§3.2).
5. **#9:** `revisar --rotular` skips the dedupe and conflict safeguards. Fix: it runs them and
   reports "já sabia" or the conflict.
6. **Catalog:** "Desinstalação …" shortcuts slip past the uninstaller filter (§4.1).

## 9. Testing

TDD and discrimination proofs as in sub-project 1 (`.claude/rules/development.md`).

- **Fakes:** one per new port in `tests/fakes/`, each with its own test.
- **Pure units:** search URL building (accents, `&`, `#`, spaces, empty), `consulta`/`site`/
  `pagina` extraction, pt-BR number formatting, screenshot naming and collision suffix, power
  command construction, catalog dedupe across kinds.
- **Power safety, schema-driven:** for every intent whose spec is a power intent (derived from
  the specs, not hand-listed): confirms at score 1.0; a "sim" leaves the learned-example count
  unchanged (re-queried from the store). Mutations proving both are recorded.
- **Repeat:** every non-repeatable intent answers "de novo" with `NothingToRepeat` (derived from
  the specs).
- **Config:** each validation rule rejected with a pt-BR message.
- **NLU fixture:** about 60 new labelled cases: every new intent, Store apps and sites through
  `abrir_app`, opposing near-ties ("aumenta o brilho" / "aumenta o volume", "pausa" /
  "próxima", "bloqueia" / "desliga"), and new out-of-domain phrases replacing "desliga o
  computador" and "pesquisa receitas de bolo", which become in-domain. Same bar; thresholds
  re-tuned only if needed, with the result recorded in `CLAUDE.md`.
- **`-m windows`** (real desktop): media toggle twice (playback ends as it started; skipped if
  no session), screenshot to a temp folder, open a Settings page, Calculator (Store) opened and
  closed, memory status. **Power actions are never executed by any test.**
- **Measurement:** idle RSS with the new dependencies loaded, recorded in `CLAUDE.md`.

### 9.1 By-hand verification (done before calling 2a complete)

Spotify and YouTube: pause, resume, next; "o que está tocando"; "tira um print"; "recorta a
tela"; "abre as configurações de bluetooth"; "brilho em 50" (result recorded either way);
"abre o youtube"; "pesquisa lofi no youtube"; "abre o whatsapp" / "fecha o whatsapp"; memory,
CPU and disk status; "bloqueia o computador" (the user unlocks); "desliga o computador" →
confirmation shown → "não".

## 10. Documentation

Local `CLAUDE.md` files updated in the same commits as the conventions they describe:
`skills` (repeatable/learnable flags, power rule), `adapters/windows` (WinRT async, Store
package folders), `nlu` (new extractors), root `CLAUDE.md` (status, fixture numbers,
measurements, by-hand results).

## 11. Unverified at design time

- Whether brightness actually changes on the monitor that reports WMI support. If not, it ships
  as `BrightnessUnsupported` and this is stated.
- WinRT wheel availability for Python 3.12 (checked during setup, before Task 1).
- Whether every Store app exposes a package install folder that its processes run from.
