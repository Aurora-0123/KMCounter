# Windows background statistics implementation

Approved design: the user-approved “KMCounter 安全整改与后台常驻方案” in this chat.
Goal: local-only normalized key/click heatmaps, per-user logon start, tray controls,
single instance, atomic five-second persistence, safe historical import and a rebuilt
windowless Windows application. Preserve GPL-3.0 and original personal records.

1. Write and run failing storage tests, then implement `StatsStore` in utils.py:
   concurrency, midnight/restart, atomic writes, corruption and idempotent import.
2. Write failing Flask tests, then implement a local-only application factory:
   Host/Origin/token protections, safe totals/rates, live status and graceful controls.
3. Write failing Windows/runtime tests, then implement tray, mutex, listeners,
   startup registration, stable user paths and deterministic shutdown.
4. Update the existing keyboard visualization with local assets, live refresh,
   status and controls. Build a windowless PyInstaller directory and installer.
5. Run unit/integration/browser tests and dependency audit; fresh code review;
   package, install, verify background process/startup registration and push to fork.

Interfaces: StatsStore snapshots use the original minute -> key -> count JSON
format. Controller exposes status, set_paused and request_stop. create_app(store,
controller) provides the existing counts routes and protected /control routes.
Runtime binds loopback before starting listeners, owns the writer/server/listeners,
and reports failures without logging keys. --background is silent, --show opens
the existing instance's page. Native registry and data installation require ordinary
user-session access; verify the actual user paths outside the redirected environment.

Review focus: write failures, existing damaged history, concurrent import/restart,
secondary launch and port conflict, endpoint protections and shutdown flushing.
