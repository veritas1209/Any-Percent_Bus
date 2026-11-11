"""Select dated and market-day services without inventing missing departures."""
from datetime import date


def departures_for(route, day, service_date=None):
    departures = route['departuresByDay'].get(day, [])
    calendar = route.get('serviceCalendar')
    if not calendar:
        return departures
    if service_date is None:
        return [] if calendar.get('onlyMonthDays') or calendar.get('startDate') else departures
    selected = date.fromisoformat(service_date)
    if calendar.get('startDate') and service_date < calendar['startDate']:
        return []
    if calendar.get('endDate') and service_date > calendar['endDate']:
        return []
    if calendar.get('onlyMonthDays') and selected.day not in calendar['onlyMonthDays']:
        return []
    if selected.day in calendar.get('exceptMonthDays', []):
        return []
    for override in calendar.get('monthDayOverrides', []):
        if selected.day in override['days']:
            return override['departures']
    return departures
