# Huddle Time Tracker

A Python CLI tool that shows how much time you've spent in Slack huddles with a colleague.

## Setup

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, name it (e.g., "Huddle Tracker"), and select your workspace
3. Go to **OAuth & Permissions**
4. Under **User Token Scopes**, add:
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `users:read`
   - `channels:read`
   - `groups:read`
   - `im:read`
5. Click **Install to Workspace** and authorize
6. Copy the **User OAuth Token** (starts with `xoxp-`)

### 2. Find Your Slack User ID

1. Open Slack, click your profile picture
2. Click **Profile**
3. Click the **...** menu and select **Copy member ID**

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in your token and user ID.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m src.main
```

You'll be prompted to search for a person or channel, then the tool will fetch all huddles and display a time report.

## Example Output

```
Huddle Time Report
========================================
Channel: John Smith (DM)
Period:  2025-01-15 -> 2026-04-07
Total huddles: 47

Date         Started By        Duration
----------------------------------------
2025-01-15   You               0h 32m
2025-01-18   John Smith        1h 05m
...

Summary
----------------------------------------
Total time:      38h 42m
Avg per huddle:  0h 49m
Longest huddle:  3h 12m
Shortest huddle: 0h 04m
```
