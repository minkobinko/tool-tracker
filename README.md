# Bitcraft Tool Upgrade Priority Tracker

This project now provides a **website** for tracking tool upgrade priorities in Bitcraft claims via the Bitjita API.

## Features

- Pulls all players in a claim.
- Pulls each player's profession XP and current tools.
- Creates a current snapshot in memory.
- Compares against a pasted historical snapshot JSON.
- Detects most active professions by XP gain.
- Ranks players by XP gained.
- Suggests missing tools based on active professions.

## Run the website

```bash
python3 webapp.py
```

Then open: <http://localhost:8000>

## How to use

1. Enter a claim ID.
2. (Optional) Enter API key.
3. (Optional) Paste a historical snapshot JSON in the text area.
4. Click **Run Tracking**.
5. View the generated priority table and current snapshot JSON.

## API assumptions

Default endpoints used by the backend logic:

- `/claims/{claim_id}/players`
- `/players/{player_id}/tools`
- `/players/{player_id}/professions`

If your Bitjita deployment uses different endpoint shapes, update defaults inside `webapp.py` or reuse the existing CLI in `bitcraft_tool_priority_tracker.py` with endpoint override flags.

## Optional CLI

The original CLI remains available for automation or cron usage:

```bash
python3 bitcraft_tool_priority_tracker.py --help
```
