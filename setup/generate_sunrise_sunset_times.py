### LOCATIONS
## WILLOW CREEK 40.93615, -123.64406
## 

import subprocess
import sys

def install_and_import(package, import_as=None):
    try:
        if import_as:
            globals()[import_as] = __import__(package)
        else:
            __import__(package)
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        if import_as:
            globals()[import_as] = __import__(package)

install_and_import("pandas")
install_and_import("astral")

from datetime import date, timedelta
import pandas as pd
from astral import LocationInfo
from astral.sun import sun

latitude = 40.93615
longitude = -123.64406
timezone = 'US/Pacific'     

start_date = date.today()
end_date = start_date + timedelta(days=365)

location = LocationInfo(name="Custom Location", region="Custom", timezone=timezone,
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

print('sun_times.csv: 1 year of times generated')