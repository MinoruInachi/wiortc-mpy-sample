from micropython import const
from pyb import I2C

class WioRTC:
    PCF8523_ADDRESS = const(0x68)
    PCF8523_CONTROL_1 = const(0x00)
    PCF8523_CONTROL_2 = const(0x01)
    PCF8523_CONTROL_3 = const(0x02)
    PCF8523_SECONDS = const(0x03)
    PCF8523_MINUTES = const(0x04)
    PCF8523_HOURS = const(0x05)
    PCF8523_DAYS = const(0x06)
    PCF8523_WEEKDAYS = const(0x07)
    PCF8523_MONTHS = const(0x08)
    PCF8523_YEARS = const(0x09)
    PCF8523_MINUTE_ALARM = const(0x0a)
    PCF8523_HOUR_ALARM = const(0x0b)
    PCF8523_DAY_ALARM = const(0x0c)
    PCF8523_WEEKDAY_ALARM = const(0x0d)
    PCF8523_OFFSET = const(0x0e)
    PCF8523_TMR_CLOCKOUT_CTRL = const(0x0f)
    PCF8523_TMR_A_FREQ_CTRL = const(0x10)
    PCF8523_TMR_A_REG = const(0x11)
    PCF8523_TMR_B_FREQ_CTRL = const(0x12)
    PCF8523_TMR_B_REG = const(0x13)

    EEPROM_ADDRESS = const(0x50)

    def __init__(self, wire=None):
        if wire is None:
            self._wire = I2C(1, I2C.MASTER)
        else:
            self._wire = wire

    def begin(self):
        self._change_reg8(PCF8523_ADDRESS, PCF8523_TMR_CLOCKOUT_CTRL,
                          0b11000111, 0b00000000)

    def set_wakeup_period(self, sec):
        if sec <= 0 or 255 < sec // 3600:
            raise ValueError("period value is bad: {}".format(sec))

	self._change_reg8(PCF8523_ADDRESS, PCF8523_TMR_CLOCKOUT_CTRL,
                          0b11111110, 0b00000000)

	if sec <= 255:
	    self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_FREQ_CTRL,
                             0b00000010)  # source for timer B is 1Hz
	    self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_REG,
                             sec)  # timer B value
	elif sec // 60 <= 255:
            self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_FREQ_CTRL,
                             0b00000011)  # source for timer B is 1/60Hz
	    self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_REG,
                             sec // 60)  # timer B value
	else:
	    self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_FREQ_CTRL,
                             0b00000100) # source for timer B is 1/3600Hz
	    self._write_reg8(PCF8523_ADDRESS, PCF8523_TMR_B_REG,
                             sec // 3600)  # timer B value

	self._change_reg8(PCF8523_ADDRESS, PCF8523_CONTROL_2, 0b00000000,
                          0b00000001)  # countdown timer B interrupt is enabled

	self._change_reg8(PCF8523_ADDRESS, PCF8523_TMR_CLOCKOUT_CTRL,
                          0b11111111, 0b00000001)  # timer B is enabled

    def shutdown(self):
	self._change_reg8(PCF8523_ADDRESS, PCF8523_TMR_CLOCKOUT_CTRL,
                          0b11111111, 0b00111000)  # CLKOUT disabled

    def eeprom_write(self, address, data):
	write_buffer = bytearray(len(data)+2)
	write_buffer[0] = (address >> 8) & 0xff
	write_buffer[1] = address & 0xff
	write_buffer[2:] = data
	self._write(EEPROM_ADDRESS, write_buffer)

    def eeprom_read(self, address, data):
	write_buffer = bytearray(2)
	write_buffer[0] = (address >> 8) & 0xff
	write_buffer[1] = address & 0xff
	self._write(EEPROM_ADDRESS, write_buffer)
	self._read(EEPROM_ADDRESS, data)

    def _write(self, slave_address, data):
        self._wire.send(data, slave_address)

    def _read(self, slave_address, data):
        self._wire.recv(data, slave_address)

    def _write_reg8(self, slave_address, reg, data):
        self._wire.mem_write(data, slave_address, reg)

    def _read_reg8(self, slave_address, reg, data):
        return self._wire.mem_read(data, slave_address, reg)

    def _change_reg8(self, slave_address, reg, and_val, or_val):
        data = bytearray(1)
        self._read_reg8(slave_address, reg, data)
        data[0] = data[0] & and_val | or_val
        self._write_reg8(slave_address, reg, data)
