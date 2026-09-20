# AlgoBot Romantic Pre-Home Splash

The romantic pre-home experience is deliberately isolated from the trading workspace. HTML structure lives in `templates/base.html`; presentation lives in `static/css/romantic_splash.css`; animation logic lives in `static/js/romantic_splash.js`; public configuration is supplied by Render environment variables.

## Render controls

Set these on the **AlgoBot web service**:

| Variable | Example | Purpose |
| --- | --- | --- |
| `ALGOBOT_SPLASH_ENABLED` | `true` | Master switch. Defaults to `false` for safe local/rollback behavior. |
| `ALGOBOT_SPLASH_PATHS_JSON` | `["/"]` | Exact URL paths that receive the splash. |
| `ALGOBOT_SPLASH_START_AT` | `2026-09-20T18:30:00+03:00` | Optional start time. Blank means immediately eligible. |
| `ALGOBOT_SPLASH_END_AT` | `2026-09-21T23:59:59+03:00` | Optional end time. Blank means no expiry. |
| `ALGOBOT_SPLASH_REPEAT` | `session` | `always`, `session`, or `once`. |
| `ALGOBOT_SPLASH_DURATION_MS` | `8200` | Total animation duration, clamped to a safe range. |
| `ALGOBOT_SPLASH_TYPE_SPEED_MS` | `42` | Typing speed. |
| `ALGOBOT_SPLASH_DELETE_SPEED_MS` | `22` | Erasing speed between messages. |
| `ALGOBOT_SPLASH_NAME` | `👑 Mäh Qűěěñ ❤️` | Name shown in the hero. |
| `ALGOBOT_SPLASH_PHONE` | `0141 322612` | Phone shown in the romantic call-to-action. |
| `ALGOBOT_SPLASH_SIGNATURE` | `With love, AlgoBot ❤️` | Closing signature. |
| `ALGOBOT_SPLASH_SIDE_LEFT` | `Always & Forever ❤️` | Left floating message. |
| `ALGOBOT_SPLASH_SIDE_RIGHT` | `I'm lucky to have you... 💕` | Right floating message. |
| `ALGOBOT_SPLASH_TAGLINE` | `Smarter trades · brighter futures · a little more love` | Brand subtitle. |
| `ALGOBOT_SPLASH_MESSAGES_JSON` | JSON array of strings | Controls exactly what is typed. |
| `ALGOBOT_SPLASH_EMOJIS_JSON` | JSON array of emoji strings | Controls the floating emoji palette. |

Example message configuration:

```json
["You're not just a user...", "You're my favourite person in this journey.", "Everything about you makes my world brighter. ❤️"]
```

Example emoji configuration:

```json
["❤️", "💖", "💕", "😍", "🌹", "✨", "👑"]
```

### Safe rollout

Keep `ALGOBOT_SPLASH_ENABLED=false` until the branch is deployed and visually checked. Turning it off is an immediate server-side rollback on the next request; no frontend code change is required.

The implementation has no trading, broker, account, API, sidebar, or strategy dependencies. It is a presentation layer that sits above the existing page shell and exits before the home page becomes interactive.
