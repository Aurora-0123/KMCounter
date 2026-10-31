# Implementation ledger — docs/implementation.md

- Fork created: Aurora-0123/KMCounter. Branch: codex/windows-background-security.
- Baseline: upstream e9e8c29; no pre-existing test suite. Existing untracked release
  extraction contains personal history and will not be staged.
- Pre-flight: storage snapshots feed API/chart; controller feeds tray/API; installer
  consumes PyInstaller output and passes an explicit legacy data directory.
- Ruling: reuse this checkout on a new codex branch, following the app's preference
  for the current checkout; no extra worktree or changes to the original main branch.
- Ruling: use Python 3.13.18 from project-local uv; system Python 3.12.0 is old.
- Task 1 complete: storage tests failed before StatsStore existed, then passed.
- Task 2 complete: create_app tests failed before implementation; 13 storage/API
  checks passed once the external CDN comment and old frontend script were removed.
- Task 3: runtime tests failed before runtime.py existed; 18 unit tests now pass.
- Ruling: legacy imports merge overlapping minute/key counts with max, not addition.
  This survives interrupted imports without double counting; independent records in
  the exact same minute are not summed, to avoid overlap with the old app.
- Ruling: browser integration requires user-session access: restricted local socket
  connections are denied. Run synthetic-data browser tests outside that restriction.
- Upgraded Plotly to the official 4.2.0 cartesian bundle, which includes bar and
  heatmap but excludes unnecessary map modules. Locked runtime dependency audit:
  no known vulnerabilities (see dependency-audit.json).
- Task 4 complete: 20 tests including real Chrome passed; packaged application
  captured F24 events, respected pause/resume, saved periodically, rejected a
  second instance and exited gracefully. Only loopback TCP connections observed.
- Ruling: explicit Windows SO_EXCLUSIVEADDRUSE is necessary; Waitress default
  reuse allowed the old Flask server to coexist and intercept browser tests.
- Final review: three Important findings reproduced and fixed in one pass:
  early-stop tray readiness, installer PID/autostart ownership, exact source snapshot.
  Regression tests failed first and then passed for the runtime/build fixes;
  installer test is run with the same process-local execution policy as install.cmd.
- Final: missing security document was already supplied during review; corrected
  the local-account security boundary wording because loopback is machine-wide.
  No remaining deferred code-review minors. Actual logon/logoff and native mouse
  hooks remain separate live validation responsibilities, not inferred from review.
- Final fix verification: 23/23 tests passed, including the installer ownership
  regression and exact source archive test. No remaining Important findings.
- Package verified: windowless PE subsystem, Python 3.13.18, matching exe/source
  SHA256 values, 149 package entries, no personal data or logs in the archive.
- Installed into the real current-user Programs directory, enabled HKCU Run, and
  verified responding PID, installed exe hash, healthy hooks, loopback binding and
  preserved/imported personal history. Original data and backup remain untouched.
- Live mouse click via the desktop skill increased both button and heatmap counts.
  Native keyboard capture, pause/resume, periodic saving and duplicate launch were
  also tested. Actual re-login remains unverified; no logoff/reboot was performed.
