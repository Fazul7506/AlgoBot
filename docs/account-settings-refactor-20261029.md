# Account Settings refactor — file-by-file change log

Date: 2026-10-29
Repository: `Fazul7506/AlgoBot`
Branch: `feature/account-settings-full-refactor-20261029`

## Baseline

- Checked out from the current `main` commit `f2fd8fc7` (merge of PR #457, which already contains the first preferences refactor).
- Working tree was clean before changes.
- Repository uses Django templates and static CSS for the four Account Settings views.
- Automated Django tests could not be run in the initial workspace because Django and pytest are not installed. This is an environment limitation, not a passing test result.
- The repository has existing account-settings, profile, preferences API, identity, MFA and security-session tests; those tests are used as the validation targets.

## File-by-file changes

| File | Layer | Verified defect | Change | Validation |
|---|---|---|---|---|
| `templates/base.html` | Frontend shell/navigation | The primary Operations navigation linked to `/operations/security/` and labelled it “Security Center”, rather than exposing Account Settings as the settings destination. | Changed that primary navigation item to `/settings/`, labelled it “Account Settings”, and added active-state handling for the settings subroutes. The operations URL remains routable. | Static diff review; automated template rendering unavailable until Django dependencies are installed. |
| `static/css/account_settings.css` | Frontend styling | Preferences controls were styled as generic controls and the identity forms did not have a consistent two-column desktop layout; page-specific responsive composition was missing. | Added shared reference-inspired preference card grids, selection states, accent swatches, notification rows, responsive stacking, and identity form/sidebar composition. | `git diff --check`; visual browser comparison not available in this environment. |
| `templates/core/security_center.html` | Frontend / information architecture | Security duplicated login activity, session inventory, event tables, generic tips, protection-check lists, broker connection and developer-access details. The banner also used a broad set of checks, including broker eligibility, to label account security. | Removed duplicated activity/session/event and unrelated operational cards from the Security page; retained MFA enrollment, verification, disablement and recovery-code actions. Reworked the overview to communicate MFA/email verification status instead of broker status. | Static template/diff review; Django template rendering and browser checks remain blocked by missing runtime dependencies. |
| `core/tests/test_account_settings_pages.py` | Tests | Test expectation required the verbose “Protection checks” section and did not assert the requested primary sidebar label. | Updated Security-page expectation and added a sidebar-label regression test. | Test code updated; not executed because Django/pytest are unavailable. |
| `core/tests/test_security_center_hardening.py` | Tests | Security-page test required duplicate Login Activity and Security Events tables that the requested information architecture removes. | Updated assertions to verify the concise Security page and absence of duplicated activity/event UI while preserving backend context assertions. | Test code updated; not executed because Django/pytest are unavailable. |

## Known gaps / blocked acceptance items

This change does not yet prove full reference-image parity or end-to-end backend correctness. In particular, the existing implementation does not expose a verified trusted-device registry, a dedicated security-alert feed, or all of the requested preference controls (layout, chart position, default page, refresh interval/frequency). These should not be represented by fabricated controls or data. Full runtime tests, mobile/desktop screenshots, API checks and deployment validation remain required before merge.


## Continued implementation on `feature/account-settings-full-refactor-20261029`

| File path | Layer | Verified issue | Change | Validation | Result |
|---|---|---|---|---|---|
| `core/views_profile.py` | Backend/view | Profile page had no computed completion percentage or user-scoped recent authentication activity in its context. | Compute completion from seven persisted fields and retrieve at most five authentication audit rows for the signed-in user; omit IP addresses. | `py_compile`; covered by 877-test full suite. | Pass |
| `templates/core/profile.html` | Frontend | Profile lacked a summary card, completion progress, quick actions and recent activity presentation. | Add summary/status/details, progress bar with ARIA values, useful settings shortcuts, and a real-event table with an empty state. | Template compile passed; screenshot comparison unavailable. | Template pass; visual blocked |
| `static/css/account_settings.css` | Frontend styling | Profile lacked the two-column summary/editor composition; new activity tables and quick links lacked responsive styling. | Add responsive profile composition, bounded horizontal table scrolling, accessible progress styling, and preference experience panel styling. | `git diff --check`; no browser viewport screenshots available. | Static pass; visual blocked |
| `templates/core/settings.html` | Frontend/API interaction | Rapid edits during an in-flight save could diverge from the submitted payload; failed saves left unsaved appearance applied. | Lock controls during saves, preserve the last server-loaded/saved form state, restore that state on save failure, and revert appearance to saved values. Add working quick links and disclose unsupported layout/refresh settings rather than rendering fake controls. | Inline JavaScript syntax check passed; API/browser tests not run. | Static pass; runtime blocked |
| `core/views_user_modules.py` | Backend/view | Security summary incorrectly counted broker connectivity and developer API-key expiry as personal account-security checks and did not derive a concise alert list. | Restrict checks to account-enabled state, email verification, secure session-cookie configuration, and MFA state; derive up to three failed/blocked sign-in alerts from real user-scoped audit events. | Python compile; focused security tests passed. | Pass |
| `templates/core/security_center.html` | Frontend | Security overview copy implied that detailed activity was shown on this page after duplicated event tables were removed; no concise alert section remained. | Point users to Login & Identity for full sign-in activity and show only genuine failed/blocked auth alerts, with a clear empty state. | 70 Django templates compiled; focused security tests passed; screenshot comparison unavailable. | Template/test pass; visual blocked |
| `core/browser_auth.py` | Backend/view | Login & Identity did not receive genuine account-scoped authentication audit records. | Pass the ten newest Authentication audit events for the signed-in user; no device, location or IP claims are made. | Python compile; account-scoped activity test passed in full suite. | Pass |
| `templates/core/account_identity.html` | Frontend | Login & Identity lacked a real login-activity section and active-session inventory was not available from the current backend. | Render real account-scoped audit events and clearly disclose that session inventory/remote revocation are unsupported rather than fabricating devices. | Inline JavaScript syntax check and Django template compilation passed; browser screenshot review unavailable. | Template pass; visual blocked |
| `core/tests/test_account_settings_pages.py` | Tests | No regression coverage for account-scoped activity, profile completion, or identity-page activity. | Add tests that distinguish the current user's authentication events from another user's events and verify completion calculation. | Python compile; focused tests and full 877-test suite passed. | Pass |
| `core/tests/test_security_center_hardening.py` | Tests | Security summary tests required unrelated broker/API-key statuses to appear as personal account-security checks and lacked alert-isolation coverage. | Assert unrelated statuses are excluded and account email/MFA checks are present; add a test proving failed-auth alerts are derived only from the signed-in user's records. | Focused suite passed; full suite rerun in progress. | Focused pass |

| `core/test_universal_workspace_access.py` | Tests | Sidebar contract expected “Security Center” as the destination label after the Account Settings route correction. | Updated the contract to require “Account Settings” at `/settings/`. | Full Django suite. | Pass |
| `core/tests/test_security_center_contract.py` | Tests | Contract tests required developer API-key expiry details to appear in the personal Security overview. | Retained the backend key-count assertion while verifying developer-key lifecycle details are not presented as account-security status. | Full Django suite. | Pass |

## Validation notes

- The initial shell image lacked Django and pip. An isolated virtual environment was bootstrapped under `/tmp/algobot-venv`; no repository dependency files were changed.
- The full test suite uses Django's temporary test database. No production database was connected or modified.
- The initial implementation pass could not inspect the reference images. The user supplied all four screenshots on 29 October 2026; browser-based visual comparison is still unverified because this environment has no browser/screenshot harness. No pixel-perfect claim is made.
- The backend has an account-scoped DB-backed session inventory and per-session revocation API; this follow-up connects them to the Login & Identity page. A trusted-device registry, dedicated security-alert feed, and persisted layout/chart/default-page/refresh preferences remain unsupported. The Security page derives a concise alert list from real failed/blocked authentication audit events; it does not claim to have a separate alert feed.


## Final local validation update (2026-10-29)

- `DJANGO_ENV=development SECRET_KEY=ci-test-secret-key CREDENTIALS_ENCRYPTION_KEY=ci-test-credentials-encryption-key DEBUG=True DJANGO_TESTING=true USE_REDIS=false python manage.py test --noinput --parallel 1`: **877 tests passed** in 227.662 seconds. The run emitted pre-existing Redis max-memory/auth-rate-limit fallback warnings, but completed with `OK`; no production database was used.
- Focused account/settings/security/navigation regression suite: **46 tests passed**.
- `python manage.py check`: passed.
- `python scripts/validate_templates.py`: 70 Django templates compiled successfully.
- `python scripts/validate_frontend_structure.py`: passed.
- `python scripts/frontend_audit.py`: completed with existing repository warnings (including inline styles/direct fetch patterns); no fatal audit failure.
- `python manage.py makemigrations --check --noinput`: passed with “No changes detected”. No migration was added.
- `python manage.py collectstatic --noinput --clear`: passed; 271 static files copied.
- `node static/js/market_asset_registry.test.js`, `node --check static/js/base_shell.js`, extracted inline-script `node --check` for the modified Settings/Profile/Login & Identity/Security templates, Python compilation, and `git diff --check`: passed.
- Additional test alignment: `core/test_universal_workspace_access.py` now expects the Account Settings navigation destination; `core/tests/test_security_center_contract.py` verifies developer-key lifecycle data remains out of the personal Security overview while the backend key count remains available in context.
- Still not verified: rendered visual comparison against the four supplied reference images at desktop/tablet/mobile sizes, and deployment/production API checks. The screenshots are now attached to the conversation, but no browser screenshot harness is available in this workspace. The PR remains a draft until visual checks and backend gaps are addressed.

- Follow-up: the Security page now presents up to three genuine failed/blocked sign-in events as concise alerts, filtered to the authenticated user's audit records. The focused security suite passed (28 tests) and the final full suite passed (878 tests).

## Follow-up: global theme and accent propagation (29 October 2026)

- Extended `static/css/account_preferences_global.css` into a shared app-wide appearance contract: light/dark surface and text tokens, form and menu surfaces, selected/active navigation, contrast-aware accent values for cyan/blue/teal/violet/amber, global density spacing, and wrapping/min-width safeguards for long content.
- `templates/base.html` now bootstraps the last explicitly selected light/dark theme from local storage before stylesheets render, loads the global theme contract after shared and page-specific stylesheets, and bumps the cache key. The existing authenticated `/api/settings/` preference loader continues to apply persisted theme, density, and accent values across routes.
- `templates/core/account_identity.html` now loads the existing authenticated `/api/security/sessions/` inventory and supports revoking individual other sessions or all other sessions. It deliberately displays only backend-provided generic device labels and expiry times, not fabricated locations or device fingerprints.
- `static/css/account_settings.css` adds responsive session rows and narrow-screen layout. `core/tests/test_account_settings_pages.py` verifies the session controls point at the real endpoint.
- Added a contract test in `core/tests/test_account_settings_pages.py` for the shared stylesheet/cache key, early theme bootstrap, all five accent values, global tokens, and text-wrapping guard.
- Validation in the working box: `node --check static/js/base_shell.js`, `scripts/validate_frontend_structure.py`, `node static/js/market_asset_registry.test.js`, and `git diff --check` passed. Django tests could not run in this box because Django is not installed in its Python environment; CI must validate the added test.
- Visual limitation: the four reference screenshots are now available and are the targets for visual review, but this environment has no installed browser/screenshot harness or Django runtime, so rendered desktop/tablet/mobile comparison remains unverified. Global theme rules cover common shell/card/form patterns; exhaustive contrast/overflow validation across every custom page still requires rendered browser testing.


## Cumulative acceptance-criteria follow-up

### Newly implemented in the current follow-up

- Extended the authenticated account-preferences API to validate and persist `layout`, `chart_position`, `default_page`, `auto_refresh_interval`, and `refresh_frequency` alongside theme, density, accent, and notification categories. Values are allow-listed server-side; unsupported options return 400 rather than being silently stored.
- Added global HTML data attributes for saved layout/chart/refresh settings and shared CSS layout hooks. The Dashboard entry point honours the saved default-page selection for Dashboard, Markets, Analysis, Terminal, or Positions. Page-specific charts must opt into the `data-chart-layout="side-by-side"` contract for chart placement rules.
- Added `TrustedDevice` model and additive migration `0016_trusted_device.py`. Device tokens are random, returned only as HttpOnly cookies, stored as SHA-256 hashes, and scoped to the authenticated user. Registration requires current-password confirmation. Users can list and revoke only their own trusted-device records.
- Added authenticated `/api/security/trusted-devices/`, `/api/security/trusted-devices/<id>/`, and `/api/security/alerts/` endpoints. The alert feed returns only the authenticated user's recorded failed/blocked/denied Authentication audit events. Security page UI can register and revoke trusted browsers and refresh its alert list from the API.
- Added tests for persistence of the additional preferences, password-gated trusted-device registration, hash-only token storage, user-scoped device revocation, and user-scoped audit alerts.

### Validation status for this follow-up

- `node --check static/js/trusted_devices.js`, `node --check static/js/base_shell.js`, `python3 -m compileall` for the modified Python modules, and `git diff --check` passed in the working box.
- Django system checks, migration checks, and Django tests could not run in the current working box because its Python environment does not have Django installed. These must be verified by GitHub Actions before the PR can leave draft status.
- No production migration or deployment has been run. Migration `0016_trusted_device.py` is additive; it creates a new table and does not drop or rewrite existing tables.
- Browser-based visual regression and desktop/tablet/mobile screenshot comparisons remain unverified. Global theme rules and the settings controls were implemented, but exhaustive review of every custom page and all hard-coded colours still requires a working browser/test deployment.
- The refresh-frequency preference is persisted and exposed globally as a data attribute, but it does not automatically reconfigure every existing market/trading data poller unless that page consumes the shared preference contract. This is still an integration acceptance item and must not be described as universally implemented yet.


| `core/models.py` | Backend/database | Adds user-scoped TrustedDevice model with hashed token, lifecycle timestamps, and revocation state | Python compile passed; Django migration check pending CI |
| `core/migrations/0016_trusted_device.py` | Database | Additive table/index migration; does not alter or delete existing records | Migration validation pending CI; not run against production |
| `core/security_settings_api.py` | Backend/API | Password-confirmed trusted-browser registration, hash-only token storage, user-scoped revoke, audit-derived alert feed | Python compile passed; Django API tests added, execution pending CI |
| `core/security_settings_urls.py` | Backend/routing | Routes trusted-device inventory/registration/revocation and security-alert feed | Django URL checks pending CI |
| `static/js/trusted_devices.js` | Frontend | Connects trusted-device UI and live alert refresh to authenticated APIs with safe DOM text rendering | Node syntax check passed; browser interaction test pending |
| `templates/core/security_center.html` | Frontend | Adds password-confirmed trusted-device management and API-backed security alerts | Template validation pending CI; visual screenshot comparison pending |
| `templates/core/settings.html` | Frontend | Adds layout, chart position, default-page and refresh preference selectors and persistence payload | Template validation pending CI; end-to-end data-poller integration remains partial |
| `core/tests/test_security_settings_api.py` | Tests | Covers password-gated registration, hash-only token, ownership isolation, revocation and alert scoping | Added; Django test execution pending CI |
| `core/tests/test_account_settings_pages.py` | Tests | Extends account preference persistence tests for layout, chart position, default page and refresh values | Added; Django test execution pending CI |


## Follow-up: contrast-tested accent foregrounds (29 October 2026)

- Corrected the Dark-theme blue accent foreground to a dark ink colour; white text on the bright blue accent did not meet WCAG AA contrast for normal-size primary-action text.
- Applied the shared `--accent-foreground` token to primary action buttons and added mathematical contrast-ratio assertions for cyan, blue, teal, violet and amber in Light and Dark palettes.
- Bumped the shared theme stylesheet cache key to `20261029-global-theme-contract4` so clients fetch the corrected CSS.
- Corrected the four-page navigation contract test to verify the global appearance stylesheet shared by all four pages rather than requiring the Profile-specific stylesheet cache key on Preferences and Security pages.
- Validation: preference runtime/contrast tests, market asset registry test, frontend structure validator, Django system check, migration check, 70-template compilation, and the focused 31-test account/security suite passed. The first focused run exposed two stale stylesheet assertions; they were corrected and the 31-test suite passed on rerun.

- Dashboard polling now consumes the saved auto-refresh interval/frequency and respects Manual mode; visibility changes no longer trigger background refresh while automatic refresh is disabled. This keeps Dashboard polling aligned with the shared preference runtime.

- Connected the persisted chart-position setting to the Analysis page's chart/insights grid: left and right positions now choose the corresponding column ordering, and bottom places the chart above the insights. Updated the Preferences copy to accurately describe which pages consume refresh scheduling and where chart position is applied; bumped the global theme/layout cache key to `20261029-global-theme-contract5`.

- Rendered the authenticated Profile page locally and found the main information area was only a launch card, leaving a large blank region compared with the reference. Replaced that placeholder with real profile fields, an accessible picture upload/drop target, supported quick actions, a security-navigation banner, and moved genuine recent activity into the right-hand content stack. Added responsive styling and template contract assertions. Local screenshots are development-only and use a synthetic local account, not production user data.

- The rendered Preferences screenshot exposed native radio circles overlaying theme/density cards and a two-column composition that pushed the profile summary below the reference position. Reworked the page into the intended three-column hierarchy (appearance/layout, notifications/data display, and profile/quick preferences/experience), added responsive two-/one-column breakpoints, token-based light-theme surfaces, and accessible selected indicators while keeping native radios keyboard-operable. Updated the shared theme cache key and acceptance assertions.

- Follow-up visual inspection tightened Preferences card density so the right-hand quick actions and experience panel fit the reference hierarchy sooner. Removed visible native radio circles from theme/density cards, added a custom checked marker that preserves keyboard focus, replaced hardcoded dark card/text colours with shared design tokens, and aligned each accent swatch to the actual Light/Dark palette values. The preference runtime test now asserts the CSS palette values and theme-aware swatch contract.

- A local Light-theme render exposed legacy `!important` dark surfaces in the sidebar, top bar and Account Settings cards, which left dark text on dark backgrounds. Added high-specificity token-based overrides for the shell, account cards, form controls and common panels while preserving semantic success/warning/error colours; expanded the CSS contract test and bumped the global theme cache key. This is a source/rendering improvement, but still requires authenticated staging validation across non-settings pages.
