Here are examples of correct extractions. Follow these patterns exactly.

## Example 1: Well-structured pantry page (high confidence)

### Input
> # Midtown Community Food Pantry
>
> **Address:** 450 Piedmont Ave NE, Atlanta, GA 30308
>
> **Hours:**
> - Monday: 9am-1pm
> - Wednesday: 9am-1pm
> - Friday: 9am-1pm
> - 2nd Saturday of each month: 10am-12pm
>
> **Requirements:**
> - Valid photo ID required
> - Proof of address in Fulton County
> - One visit per household per week
>
> **Note:** Closed for Thanksgiving week (Nov 25-29). Please arrive by 12:30pm as we close doors at capacity.

### Expected Output
```json
{
  "status": "OPEN",
  "hours_notes": "Mon 9am-1pm, Wed 9am-1pm, Fri 9am-1pm, 2nd Sat 10am-12pm",
  "hours_today": "[depends on current day]",
  "eligibility_rules": ["Valid photo ID required", "Proof of address in Fulton County", "One visit per household per week"],
  "is_id_required": true,
  "residency_req": "Fulton County",
  "special_notes": "Closed for Thanksgiving week (Nov 25-29). Arrive by 12:30pm, closes at capacity.",
  "confidence": 9
}
```

## Example 2: Generic church page with food mention (low confidence)

### Input
> # First Baptist Church of Atlanta
>
> Welcome to our church! We have been serving the community since 1952.
>
> **Our Ministries:**
> - Youth Ministry
> - Music Ministry
> - Food Ministry - helping feed our neighbors
> - Senior Care
>
> **Sunday Services:** 9am and 11am
> **Wednesday Bible Study:** 7pm
>
> Contact us at (404) 555-0100

### Expected Output
```json
{
  "status": "OPEN",
  "hours_notes": "Not listed on website",
  "hours_today": "Hours not listed",
  "eligibility_rules": ["Open to all - no restrictions listed"],
  "is_id_required": false,
  "residency_req": null,
  "special_notes": null,
  "confidence": 3
}
```

## Example 3: Pantry with appointment-only access (waitlist)

### Input
> # Hope Center Food Distribution
>
> We provide emergency food boxes to families in need.
>
> **How to receive food:**
> 1. Call (404) 555-0200 to schedule an appointment
> 2. Appointments available Tuesday and Thursday, 10am-3pm
> 3. Limited to 15 families per day
> 4. Must bring proof of residency in DeKalb County
>
> Due to high demand, there may be a 1-2 week wait for new appointments.

### Expected Output
```json
{
  "status": "WAITLIST",
  "hours_notes": "Tue 10am-3pm, Thu 10am-3pm (by appointment only)",
  "hours_today": "[depends on current day - appointment only]",
  "eligibility_rules": ["By appointment only - call (404) 555-0200", "Limited to 15 families per day", "Must bring proof of residency in DeKalb County"],
  "is_id_required": true,
  "residency_req": "DeKalb County",
  "special_notes": "1-2 week wait for new appointments due to high demand",
  "confidence": 8
}
```

## Example 4: Temporarily closed pantry

### Input
> # Southside Community Pantry
>
> ~~Open Mondays and Wednesdays 2pm-5pm~~
>
> **NOTICE: Our food pantry is temporarily closed due to building renovations. We expect to reopen in March 2026. For immediate food assistance, please contact the Atlanta Community Food Bank at (404) 555-0300.**
>
> We normally serve residents of zip codes 30310-30315.

### Expected Output
```json
{
  "status": "CLOSED",
  "hours_notes": "Normally Mon & Wed 2pm-5pm (TEMPORARILY CLOSED for renovations)",
  "hours_today": "Closed today",
  "eligibility_rules": ["Serves residents of zip codes 30310-30315"],
  "is_id_required": false,
  "residency_req": "Zip codes 30310-30315",
  "special_notes": "Temporarily closed for building renovations. Expected to reopen March 2026. Contact Atlanta Community Food Bank at (404) 555-0300 for immediate assistance.",
  "confidence": 7
}
```
