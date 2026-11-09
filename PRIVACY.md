# Privacy Notice (DRAFT — not legal advice)

**This is a draft written for development purposes, not a reviewed legal
document.** It describes what the AlphaGo backend actually does with
data, as implemented, so that whoever publishes a real privacy notice has
an accurate starting point. Have this reviewed by a lawyer, and update it
to match whatever the actual production deployment does (hosting
provider, analytics, any third parties added later) before it's shown to
real users.

## What we collect

When you open the AlphaGo Mini App through Telegram, we receive and store:

- Your Telegram user id, username, first name, last name, and profile photo URL (whichever of these Telegram provides — not all fields are required).
- Your Telegram-reported language.
- Gameplay data you generate: scores, session timing, XP earned, achievements unlocked, check-in streaks, tasks completed, referrals, challenges, favorites, and ratings you give games.
- Technical data needed to operate the service: timestamps, and (if the server logs it) IP address and request metadata for abuse prevention.

We do not collect your phone number, precise location, payment details, or message content — we only receive what Telegram's Mini App `initData` mechanism provides when you open the app, which is limited to the fields above.

## What we don't do

- We don't sell your data.
- We don't use your data for advertising targeting.
- We don't share your data with third parties except as described below.

## Sponsored tasks

Some in-app tasks may be sponsored by a third party. Completing a sponsored task may generate an aggregate completion count visible to that sponsor; we do not share your individual identity (username, Telegram id) with sponsors.

## How long we keep data

Gameplay history (scores, XP) is kept indefinitely as the basis for your level, leaderboard rank, and achievements, unless you delete your account (see below). Personally identifying fields (username, name, photo) are removed immediately on deletion; gameplay history stays in anonymized form so leaderboards and the XP ledger stay internally consistent.

## Your choices

- **Change your language or notification settings** at any time from the app's settings.
- **Delete your account**: send `DELETE /me` through the app (or ask in-app for this to be done for you). This immediately removes your username, name, and profile photo from our database. Your gameplay history stays, but with no way to identify it as yours. Reopening the Mini App afterward creates a fresh profile under your Telegram id.

## Security

Data is stored in a private database not directly exposed to the internet. Access is authenticated through Telegram's own `initData` signing mechanism — nobody can act as "you" without a signed request from Telegram itself (or a currently-valid access token your Telegram session obtained from us). See the project's internal security documentation for engineering detail.

## Contact

_Add a real contact method (email or Telegram handle) here before publishing._
