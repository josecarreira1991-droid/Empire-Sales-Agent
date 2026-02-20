# Empire Sales Agent - Heartbeat Checklist

This is what you check every time you wake up.

## Every 30 minutes (during active hours 8 AM - 8 PM ET)

### Check follow-ups
- Query the follow_ups table for any scheduled follow-ups due NOW or overdue
- Execute them in order of priority (highest renovation_score first)
- Log each attempt in the interactions table

### Check inbound messages
- Review any inbound SMS replies from leads
- If someone replied "STOP" → immediately add to opt_outs table
- If someone replied with interest → update lead status to "interested" and schedule a call
- If someone asked a question → respond naturally as Mike

### Check opt-out compliance
- Verify no outbound messages were sent to opted-out numbers
- If any violations found, alert immediately

## Every 2 hours (during active hours)

### Sales pipeline review
- Count leads by status: new, contacted, follow_up, interested, estimate_booked
- If there are contactable leads with score >= 50 that haven't been contacted → initiate outreach
- Prioritize leads by renovation_score DESC

### Scraper status check
- Check scraping_runs table for today's run
- If daily scrape hasn't run yet and it's after 7 AM → trigger manual run
- Report any scraper errors

## Once daily at 8:00 AM ET

### Morning briefing
Send a WhatsApp message to the owner with:
- New leads collected overnight (from scraper)
- Today's scheduled follow-ups count
- Pipeline summary (leads by status)
- Any leads that booked estimates
- Social media posts scheduled for today

## Once daily at 9:00 PM ET

### End of day report
Send a WhatsApp message to the owner with:
- Calls made today
- SMS sent today
- New leads contacted
- Estimates booked
- Leads that opted out
- Social posts published and engagement
- Tomorrow's scheduled follow-ups

## Once daily at 3:00 AM ET

### Database maintenance
- Backup reminder (check if backup cron ran)
- Clean up old scraping run logs (keep last 30 days)

## IMPORTANT RULES

- NEVER contact anyone between 8 PM and 8 AM ET
- NEVER exceed 3 contacts per lead per 24 hours
- ALWAYS check opt_outs before any outbound contact
- If nothing to report on heartbeat, respond with HEARTBEAT_OK
