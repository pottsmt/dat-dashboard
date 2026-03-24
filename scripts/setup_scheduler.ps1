# Setup Windows Task Scheduler for DAT Dashboard Daily Run

# Remove existing task if it exists
Unregister-ScheduledTask -TaskName "DAT Dashboard Daily Run" -Confirm:$false -ErrorAction SilentlyContinue

# Create the scheduled task action
$action = New-ScheduledTaskAction -Execute "python" `
    -Argument "C:\Users\Matthew\claude-projects\dat-dashboard\scripts\daily_auto.py" `
    -WorkingDirectory "C:\Users\Matthew\claude-projects\dat-dashboard"

# Create weekday trigger at 9:30 AM (Monday through Friday)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "9:30AM"

# Settings: Start when available (if computer was off at scheduled time)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# Register the task
Register-ScheduledTask -TaskName "DAT Dashboard Daily Run" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs DAT Dashboard daily workflow: SEC scan, Bloomberg export, dashboard generation"

Write-Host "Scheduled task created successfully!"
Write-Host "Task will run daily at 9:30 AM"
