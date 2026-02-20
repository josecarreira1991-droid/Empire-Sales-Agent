---
name: lead-manager
description: "Manages the lead database. Use to query leads, update statuses, view pipeline reports, search for specific leads, export data, and get statistics. This is the central skill for all database operations on leads."
tools:
  - Bash
  - Read
---

# Lead Manager - Database Operations

Manage all leads in the Empire Sales Agent PostgreSQL database.

## Common Queries

### View pipeline summary:
```bash
psql -U empire -d empire_leads -c "
SELECT status, COUNT(*) as count, ROUND(AVG(renovation_score)) as avg_score
FROM leads WHERE do_not_call = false
GROUP BY status ORDER BY count DESC
"
```

### Get top leads ready to contact:
```bash
psql -U empire -d empire_leads -c "SELECT id, full_name, phone, city, county, renovation_score, status FROM contactable_leads LIMIT 20"
```

### Search leads by name or phone:
```bash
psql -U empire -d empire_leads -c "SELECT * FROM leads WHERE full_name ILIKE '%SEARCH_TERM%' OR phone LIKE '%SEARCH_TERM%'"
```

### View leads by county:
```bash
psql -U empire -d empire_leads -c "SELECT id, full_name, phone, city, renovation_score, status FROM leads WHERE county = 'Lee' AND status = 'new' ORDER BY renovation_score DESC LIMIT 20"
```

### View recent interactions for a lead:
```bash
psql -U empire -d empire_leads -c "SELECT i.*, l.full_name FROM interactions i JOIN leads l ON i.lead_id = l.id WHERE i.lead_id = LEAD_ID ORDER BY i.created_at DESC"
```

### Today's activity:
```bash
psql -U empire -d empire_leads -c "
SELECT type, direction, status, COUNT(*) FROM interactions
WHERE created_at::date = CURRENT_DATE GROUP BY type, direction, status
"
```

### Leads added today:
```bash
psql -U empire -d empire_leads -c "SELECT id, full_name, phone, source, renovation_score FROM leads WHERE created_at::date = CURRENT_DATE ORDER BY renovation_score DESC"
```

## Update Operations

### Update lead status:
```bash
psql -U empire -d empire_leads -c "UPDATE leads SET status = 'NEW_STATUS' WHERE id = LEAD_ID"
```

### Book an estimate:
```bash
psql -U empire -d empire_leads -c "UPDATE leads SET status = 'estimate_booked', notes = 'Estimate scheduled for DATE at TIME' WHERE id = LEAD_ID"
```

### Add lead manually:
```bash
psql -U empire -d empire_leads -c "
INSERT INTO leads (full_name, phone, address, city, county, source, status, renovation_score)
VALUES ('NAME', 'PHONE', 'ADDRESS', 'CITY', 'COUNTY', 'manual', 'new', 50)
"
```

### Mark as do-not-call:
```bash
psql -U empire -d empire_leads -c "
UPDATE leads SET do_not_call = true, status = 'do_not_call' WHERE id = LEAD_ID;
INSERT INTO opt_outs (phone, source) SELECT phone, 'manual' FROM leads WHERE id = LEAD_ID ON CONFLICT DO NOTHING;
"
```

## Export

### Export leads to CSV:
```bash
psql -U empire -d empire_leads -c "\COPY (SELECT * FROM leads WHERE status IN ('interested', 'estimate_booked') ORDER BY renovation_score DESC) TO '/tmp/hot_leads.csv' CSV HEADER"
```

### Export daily report:
```bash
psql -U empire -d empire_leads -c "\COPY (
SELECT l.full_name, l.phone, l.city, l.county, l.renovation_score, l.status,
       COUNT(i.id) as total_interactions,
       MAX(i.created_at) as last_contact
FROM leads l LEFT JOIN interactions i ON l.id = i.lead_id
WHERE l.created_at::date = CURRENT_DATE OR i.created_at::date = CURRENT_DATE
GROUP BY l.id ORDER BY l.renovation_score DESC
) TO '/tmp/daily_report.csv' CSV HEADER"
```

## Statistics

### Full pipeline stats:
```bash
psql -U empire -d empire_leads -c "
SELECT
  (SELECT COUNT(*) FROM leads) as total_leads,
  (SELECT COUNT(*) FROM leads WHERE status = 'new') as new_leads,
  (SELECT COUNT(*) FROM leads WHERE status = 'interested') as interested,
  (SELECT COUNT(*) FROM leads WHERE status = 'estimate_booked') as estimates_booked,
  (SELECT COUNT(*) FROM leads WHERE status = 'closed_won') as closed_won,
  (SELECT COUNT(*) FROM opt_outs) as opted_out,
  (SELECT COUNT(*) FROM interactions WHERE created_at::date = CURRENT_DATE) as today_interactions
"
```
