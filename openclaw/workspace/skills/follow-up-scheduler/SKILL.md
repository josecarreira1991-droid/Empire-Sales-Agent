---
name: follow-up-scheduler
description: "Manages the follow-up cadence for leads. Schedules calls and SMS at optimal intervals, tracks attempt counts, and ensures compliance with Florida FTSA limits. Use to schedule, view, or modify follow-up sequences."
tools:
  - Bash
---

# Follow-Up Scheduler - Automated Contact Cadence

Manages the timing and sequence of follow-up contacts for each lead.

## Standard Follow-Up Cadence

After initial contact, follow this sequence:

| Day | Action | Template |
|-----|--------|----------|
| Day 0 | Initial call | sales-caller opening script |
| Day 1 | SMS if no answer | "Tried calling" message |
| Day 3 | Second call | Follow-up call script |
| Day 5 | SMS with value | Tip or value-add message |
| Day 7 | Third call | Final call attempt |
| Day 10 | SMS with offer | Special offer or urgency |
| Day 14 | Final SMS | Last touch, save our number |

After Day 14 with no response → move lead to status 'closed_lost'.

## Schedule a follow-up

### After a missed call (schedule SMS for next day):
```bash
psql -U empire -d empire_leads -c "
INSERT INTO follow_ups (lead_id, scheduled_at, type, attempt_number, message_template)
VALUES (LEAD_ID, NOW() + INTERVAL '1 day', 'sms', 1, 'missed_call')
"
```

### After a conversation (schedule follow-up call):
```bash
psql -U empire -d empire_leads -c "
INSERT INTO follow_ups (lead_id, scheduled_at, type, attempt_number, message_template)
VALUES (LEAD_ID, NOW() + INTERVAL '3 days', 'call', 2, 'follow_up')
"
```

### Schedule full cadence for a new lead:
```bash
psql -U empire -d empire_leads -c "
INSERT INTO follow_ups (lead_id, scheduled_at, type, attempt_number, message_template) VALUES
  (LEAD_ID, NOW() + INTERVAL '1 day', 'sms', 1, 'missed_call'),
  (LEAD_ID, NOW() + INTERVAL '3 days', 'call', 2, 'follow_up'),
  (LEAD_ID, NOW() + INTERVAL '5 days', 'sms', 2, 'value_add'),
  (LEAD_ID, NOW() + INTERVAL '7 days', 'call', 3, 'final_call'),
  (LEAD_ID, NOW() + INTERVAL '10 days', 'sms', 3, 'offer'),
  (LEAD_ID, NOW() + INTERVAL '14 days', 'sms', 4, 'final_touch')
"
```

## View upcoming follow-ups

### Today's follow-ups:
```bash
psql -U empire -d empire_leads -c "
SELECT f.id, f.scheduled_at, f.type, f.attempt_number, l.full_name, l.phone, l.renovation_score
FROM follow_ups f JOIN leads l ON f.lead_id = l.id
WHERE f.completed = false AND f.scheduled_at::date = CURRENT_DATE
ORDER BY f.scheduled_at
"
```

### Overdue follow-ups:
```bash
psql -U empire -d empire_leads -c "
SELECT f.id, f.scheduled_at, f.type, l.full_name, l.phone
FROM follow_ups f JOIN leads l ON f.lead_id = l.id
WHERE f.completed = false AND f.scheduled_at < NOW()
ORDER BY f.scheduled_at
"
```

### This week's schedule:
```bash
psql -U empire -d empire_leads -c "
SELECT f.scheduled_at::date as day, f.type, COUNT(*) as count
FROM follow_ups f
WHERE f.completed = false AND f.scheduled_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
GROUP BY f.scheduled_at::date, f.type ORDER BY day
"
```

## Complete a follow-up

After executing a scheduled follow-up:
```bash
psql -U empire -d empire_leads -c "
UPDATE follow_ups SET completed = true, completed_at = NOW(), result = 'RESULT'
WHERE id = FOLLOWUP_ID
"
```

## Cancel follow-ups for a lead

When a lead opts out or books an estimate:
```bash
psql -U empire -d empire_leads -c "
UPDATE follow_ups SET completed = true, result = 'cancelled_REASON'
WHERE lead_id = LEAD_ID AND completed = false
"
```

## Compliance checks

### Before executing ANY follow-up:
1. Check if lead is in opt_outs table
2. Check daily contact count < 3
3. Check current time is between 8 AM - 8 PM ET
4. If ANY check fails → skip this follow-up and mark as 'skipped_compliance'

### If a lead opts out mid-cadence:
- Cancel ALL remaining follow-ups immediately
- Add to opt_outs
- Update lead status to 'do_not_call'
