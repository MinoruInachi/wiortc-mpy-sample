from wiolte import wiolte, LTEModule
from wiortc import WioRTC
from micropython import const


BOOT_INTERVAL = const(30)  # [sec.]

pyb.delay(200)
print('--- START ---------------------------------------------------')

print('### ### I/O Initialize.')
wiolte.initialize()

print('### Power supply ON.')
wiolte.set_grove_power(True)
pyb.delay(500)

# Device initialize
print('### Device initialize.')
i2c = pyb.I2C(1, pyb.I2C.MASTER)
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
        beep = pyb.Pin('D38', pyb.Pin.OUT_PP)
        beep.high()
        pyb.delay(200)
        beep.low()

        print('Shutdown.')
        rtc.set_wakeup_period(BOOT_INTERVAL)
        rtc.shutdown()
        pyb.delay(500)
    finally:
        pyb.delay(BOOT_INTERVAL*1000)
