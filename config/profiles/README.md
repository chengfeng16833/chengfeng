# Strategy Profiles

This directory holds normalized profile data migrated from `C:\Users\ChengFeng\Desktop\Starsavior-master\profiles`.

Profile kinds:

- `training`: rule-engine profiles for training choice scoring.
- `events`: event option and hotkey profiles.
- `shop`: shop item priority profiles.
- `skills`: journey-end skill priority profiles.

The loader only accepts JSON objects. Runtime code should keep existing hard-coded behavior as a fallback until each profile kind is integrated and covered by tests.
