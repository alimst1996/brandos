# BrandOS Autopilot Recovery Runbook

Non-technical guide for recovering the BrandOS continuous delivery autopilot
after a disruption (Hermes restart, Windows reboot, or network outage).

## What Is Running

The autopilot has two scheduled jobs:

1. **Dispatcher** (`f8da63a67f85`) - runs every 15 minutes
   - Checks Jira for eligible issues
   - Creates kanban tasks up to WIP limit of 2
   - Reviews and routes completed work

2. **Daily Report** (`9c5bc3373ac7`) - runs at 09:00 Europe/Berlin
   - Gathers board statistics
   - Sends executive summary to Telegram

## How to Check If Autopilot Is Running

Open a terminal and run:

```
hermes cron list
```

You should see both jobs listed as `enabled`. If either shows `paused`,
run `hermes cron resume <job_id>`.

## How to Restart After Hermes/Windows Restart

Hermes cron jobs persist in the database. After a restart:

1. Check gateway is running: `hermes gateway status`
2. If not running: `hermes gateway install` (installs as Windows service)
3. Check cron scheduler: `hermes cron status`
4. If scheduler not running, it starts automatically with the gateway
5. Verify jobs: `hermes cron list`

No manual re-creation of jobs is needed.

## How to Check Kanban Board

```
hermes kanban list
hermes kanban stats
```

Active tasks should never exceed 2. If you see more, run:
```
hermes kanban reclaim <task_id>
```
to release stuck tasks.

## How to Manually Trigger a Dispatch

If the dispatcher missed a cycle or you want to force a check:

```
hermes cron run f8da63a67f85
```

## How to Manually Trigger the Daily Report

```
hermes cron run 9c5bc3373ac7
```

## How to Pause/Resume the Autopilot

Pause (e.g., during maintenance):
```
hermes cron pause f8da63a67f85
hermes cron pause 9c5bc3373ac7
```

Resume:
```
hermes cron resume f8da63a67f85
hermes cron resume 9c5bc3373ac7
```

## How to Check for Stale Tasks

Tasks running longer than 4 hours are considered stale. Check:
```
hermes kanban stats
```

If a task is stuck:
```
hermes kanban reclaim <task_id>
```

The dispatcher will automatically re-assign on its next cycle.

## How to View Dispatcher Logs

Each cron run creates a session. View recent runs:
```
hermes cron runs
```

## How to Change the WIP Limit

Edit `scripts/autopilot-dispatcher.py` and change `WIP_LIMIT = 2` to
the desired value. Then commit and push.

## How to Change the Daily Report Time

Edit the cron expression on job `9c5bc3373ac7`:
```
hermes cron edit 9c5bc3373ac7
```
Set the new schedule (e.g., `0 10 * * *` for 10:00).

## How to Add/Remove Eligible Issues

In Jira, add/remove the `ready-for-dispatch` label. The dispatcher
will pick up changes on its next 15-minute cycle.

To block an issue from dispatch, add the `do-not-dispatch-yet` label.

## Emergency Stop

To completely stop the autopilot:
```
hermes cron pause f8da63a67f85
hermes cron pause 9c5bc3373ac7
```

To re-enable:
```
hermes cron resume f8da63a67f85
hermes cron resume 9c5bc3373ac7
```

## Cron Job IDs Reference

| Job | ID | Schedule |
|-----|-----|----------|
| Dispatcher | `f8da63a67f85` | `*/15 * * * *` |
| Daily Report | `9c5bc3373ac7` | `0 9 * * *` |
