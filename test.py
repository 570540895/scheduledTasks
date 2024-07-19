import sched
import time
from datetime import datetime

dt1 = datetime.now()
dt2 = time.time()

def print_time():
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


schedule = sched.scheduler(time.time, time.sleep)
schedule.enter(3, 0, print_time, ())
schedule.enter(10, 0, print_time, ())
schedule.run()
