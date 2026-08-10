"""Constants for the APS Usage integration."""

DOMAIN = "aps_usage"

# Update interval: every hour (APS data refreshes daily, not real-time)
UPDATE_INTERVAL_SECONDS = 3600

# Days of daily usage history to fetch (60 gives ~2 billing cycles)
DAYS_OF_HISTORY = 60

# Long-term statistics: how many days of hourly history to backfill on the
# first run (one API request per day, so keep this modest)
STATS_BACKFILL_DAYS = 30

# Days at the tail of the statistics to re-fetch when new data appears, so
# estimated readings that APS later corrects get rewritten
STATS_OVERLAP_DAYS = 2

# Upper bound on days fetched in a single statistics run (gap recovery cap)
STATS_MAX_DAYS_PER_RUN = 60
