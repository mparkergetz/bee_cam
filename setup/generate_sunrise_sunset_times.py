import sys
from datetime import date, timedelta
import pandas as pd
from astral import LocationInfo
from astral.sun import sun

locations = {
    "talking_trees": {
        "latitude": 40.93615,
        "longitude": -123.64406,
        "timezone": "US/Pacific"
    },
    "sunrise_mountain": {
        "latitude": 40.94774,
        "longitude": -123.68905,
        "timezone": "US/Pacific"
    },
    "emerald_queen": {
        "latitude": 40.89297,
        "longitude": -123.64952,
        "timezone": "US/Pacific"
    }
}

if len(sys.argv) != 2 or sys.argv[1] not in locations:
    print("Usage: python3 generate_sunrise_sunset_times.py [talking_trees|sunrise_mountain|emerald_queen]")
    sys.exit(1)

loc = locations[sys.argv[1]]
latitude = loc["latitude"]
longitude = loc["longitude"]
timezone = loc["timezone"]

start_date = date.today()
end_date = start_date + timedelta(days=365)

location = LocationInfo(name=sys.argv[1], region="Custom", timezone=timezone,
                        latitude=latitude, longitude=longitude)

current = start_date
data = []

while current <= end_date:
    s = sun(location.observer, date=current, tzinfo=location.timezone)
    data.append({
        'date': current,
        'sunrise': s['sunrise'].strftime('%H:%M:%S'),
        'sunset': s['sunset'].strftime('%H:%M:%S')
    })
    current += timedelta(days=1)

df = pd.DataFrame(data)
df.to_csv("sun_times.csv", index=False)

print(f'sun_times.csv: 1 year of times generated for {sys.argv[1]}')