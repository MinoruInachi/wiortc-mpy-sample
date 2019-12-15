from wiolte import wiolte
from wiortc import WioRTC
from micropython import const
from machine import Pin, I2C
import time


BOOT_INTERVAL = const(30)  # [sec.]

time.sleep_ms(200)
print('--- START ---------------------------------------------------')

print('### ### I/O Initialize.')
wiolte.initialize()

print('### Power supply ON.')
wiolte.set_grove_power(True)
time.sleep_ms(500)

# Device initialize
print('### Device initialize.')
i2c = I2C('I2C')
rtc = WioRTC(i2c)
rtc.begin()

print('### Completed.')

while True:
    try:
        val = bytearray(1)
        rtc.eeprom_read(0, val)
        print("EEPROM value is " + str(val[0]))

        val[0] += 1
        rtc.eeprom_write(0, val)

        print('Beep.')
        beep = Pin('D38', Pin.OUT)
        beep.high()
        time.sleep_ms(200)
        beep.low()

        print('Shutdown.')
        rtc.set_wakeup_period(BOOT_INTERVAL)
        rtc.shutdown()
        time.sleep_ms(500)
    finally:
        time.sleep(BOOT_INTERVAL)
