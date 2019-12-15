from machine import Pin, UART
from time import ticks_ms, ticks_diff

class WioLTE:
    """The WioLTE class to control Wio LTE on-board functions."""
    def __init__(self):
        self.__comm = None
        self.__pin_grove_power = Pin('GRO_POWR')
        
    def initialize(self):
        """Initialize Wio LTE board."""
        self.__pin_grove_power.init(Pin.OUT)
        self.__pin_grove_power.off()

    def get_comm(self):
        """Gets communication module object."""
        if self.__comm is None:
            self.__comm = LTEModule()
        return self.__comm

    def set_grove_power(self, turn_on):
        """Turn on or off the power supply of Grove connectors."""
        self.__pin_grove_power.value(turn_on)


class LTEModuleError(RuntimeError):
    """Raised when a LTEModule-related error occurs."""
    def __init__(self, message:str):
        super().__init__(message)


class LTEModule(object):
    """Controls Quectel EC21 LTE Module."""
    CR = const(0x0d)
    LF = const(0x0a)

    SOCKET_TCP = const(0)
    SOCKET_UDP = const(1)

    MAX_CONNECT_ID = const(12)
    MAX_SOCKET_DATA_SIZE = const(1460)

    def __init__(self):
        self.__pin_reset_module = Pin('RESET_MODULE')
        self.__pin_dtr_module = Pin('DTR_MODULE')
        self.__pin_pwrkey_module = Pin('PWRKEY_MODULE')
        self.__pin_module_power = Pin('M_POWR')
        self.__pin_module_status = Pin('STATUS')
        self.__pin_disable_module = Pin('W_DISABLE')
        self.__pin_wakeup_module = Pin('WAKEUP_IN')
        
        self.__uart = UART('LTE')
        self.__urcs = None
        self.__connections = []

        from uasyncio import sleep_ms, CancelledError
        self.sleep_ms = sleep_ms
        self.CancelledError = CancelledError

    def initialize(self):
        """
        Initialize I/O ports and peripherals to communicate
        with the module.
        """
        self.__pin_reset_module.init(Pin.OUT)
        self.__pin_dtr_module.init(Pin.OUT)
        self.__pin_pwrkey_module.init(Pin.OUT)
        self.__pin_module_power.init(Pin.OUT)
        self.__pin_module_status.init(Pin.IN)
        self.__pin_disable_module.init(Pin.OUT)
        self.__pin_wakeup_module.init(Pin.OUT)

        self.__pin_dtr_module.off()
        self.__pin_pwrkey_module.off()
        self.__pin_module_power.off()
        self.__pin_reset_module.on()
        self.__pin_disable_module.on()
        self.__pin_wakeup_module.off()
        
        self.__uart.init(baudrate=115200, timeout=5000, timeout_char=1000)

    def set_supply_power(self, to_supply):
        """Enable/Disable power supply to the module."""
        self.__pin_module_power.value(1 if to_supply else 0)

    async def reset(self):
        """Reset the module."""
        self.__pin_reset_module.off()
        await self.sleep_ms(200)
        while self.__uart.any():
            self.__uart.read(self.__uart.any())
        self.__pin_reset_module.on()
        await self.sleep_ms(300)

        for trial in range(15):
            if await self.wait_response(b'RDY') is not None:
                return True
        return False

    async def wait_busy(self, max_trials=50):
        """Wait while the module is busy."""
        for trial in range(max_trials):
            if not self.is_busy():
                return True
            await self.sleep_ms(100)
        return False

    async def turn_on(self):
        """Turn on the module."""
        await self.sleep_ms(100)
        self.__pin_pwrkey_module.on()
        await self.sleep_ms(200)
        self.__pin_pwrkey_module.off()

        if not await self.wait_busy():
            return False

        for trial in range(15):
            if await self.wait_response(b'RDY') is not None:
                return True
        return False

    async def turn_on_or_reset(self):
        """
        Turn on or reset the module and wait until the LTE
        commucation gets available.
        """
        self.__urcs = []

        if self.is_busy():
            if not await self.turn_on():
                return False
        else:
            if not await self.reset():
                return False

        # Check if the module can accept commands.
        if not await self.write_command_wait(b'AT', b'OK'):
            return False
        # Disable command echo
        if not await self.write_command_wait(b'ATE0', b'OK'):
            return False
        # Use UART1 port to receive URC
        if not await self.write_command_wait(b'AT+QURCCFG="urcport","uart1"', b'OK'):
            return False

        buffer = bytearray(1024)
        result, responses = await self.execute_command(b'AT+QSCLK=1', buffer, expected_response_list=[b'OK', b'ERROR'])
        if not result:
            return False
        
        while True:
            result, responses = await self.execute_command(b'AT+CPIN?', buffer, timeout=1000)
            if len(responses) == 0: return False
            if result:
                return True
    
    async def get_IMEI(self):
        """Gets International Mobile Equipment Identity (IMEI)"""
        response = await self.execute_command_single_response(b'AT+GSN')
        return str(response, 'utf-8') if response is not None else None
    
    async def get_IMSI(self):
        """Gets International Mobile Subscriber Identity (IMSI)"""
        response = await self.execute_command_single_response(b'AT+CIMI')
        return str(response, 'utf-8') if response is not None else None

    async def get_phone_number(self):
        "Gets phone number (subscriber number)"
        response = await self.execute_command_single_response(b'AT+CNUM', b'+CNUM:')
        return str(response[6:], 'utf-8') if response is not None else None

    async def get_RSSI(self):
        "Gets received signal strength indication (RSSI)"
        response = await self.execute_command_single_response(b'AT+CSQ', b'+CSQ:')
        if response is None:
            return None
        try:
            s = str(response[5:], 'utf-8')
            rssi, ber = s.split(',', 2)
            return (int(rssi), int(ber))
        except ValueError:
            return None

    async def activate(self, access_point:str, user:str, password:str, timeout:int=None):
        #print("Activating network...")
        while True:
            # Read network registration status.
            response = await self.execute_command_single_response(b'AT+CGREG?', b'+CGREG:', timeout)
            if response is None:
                raise LTEModuleError('Failed to get registration status.')
            s = str(response, 'utf-8')
            #print('AT+CGREG?:{}'.format(s))
            n, stat = s.split(',')[:2]
            if stat == '0' or stat == '4':  # Not registered and not searching (0), or unknown (4).
                #raise LTEModuleError('Invalid registration status.')
                pass
            elif stat == '1' or stat == '5': # Registered.
                break
        
        while True:
            # Read EPS network registration status
            response = await self.execute_command_single_response(b'AT+CEREG?', b'+CEREG:', timeout)
            if response is None:
                raise LTEModuleError('Failed to get registration status.')
            s = str(response, 'utf-8')
            #print('AT+CEREG?:{}'.format(s))
            n, stat = s.split(',')[:2]
            if stat == '0' or stat == '4':  # Not registered and not searching (0), or unknown (4).
                raise LTEModuleError('Invalid registration status.')
            elif stat == '1' or stat == '5': # Registered.
                break
        # Configure TCP/IP contect parameters
        # contextID,context_type,APN,username,password,authentication
        # context_type  : IPv4 = 1, IPv4/v6 = 2
        # authentication: None = 0, PAP = 1, CHAP = 2, PAP or CHAP = 3
        command = bytes('AT+QICSGP=1,1,"{0}","{1}","{2}",1'.format(access_point, user, password), 'utf-8')
        if not await self.write_command_wait(command, b'OK', timeout):
            return False
        # Activate a PDP context
        if not await self.write_command_wait(b'AT+QIACT=1', b'OK', timeout):
            return False
        if not await self.write_command_wait(b'AT+QIACT?', b'OK', timeout):
            return False
        
        return True
    
    async def get_ip_address(self, host:str, timeout:int=60*1000) -> List[str]:
        """
        Get IP address from hostname using DNS.

        :param str host:        An address of the remote host.  
        :return:                A list of IP addresses corresponding to the hostname.
        :raises LTEModuleError: If the communication module failed to open a new socket.
        """
        assert(host is not None)
        
        await self.__process_remaining_urcs(timeout=timeout)

        buffer = bytearray(1024)

        try:
            # Query host address.
            command = bytes('AT+QIDNSGIP=1,"{0}"'.format(host), 'utf-8')
            if not await self.write_command_wait(command, b'OK', timeout=timeout):
                raise LTEModuleError('Failed to get IP.')

            response = await self.wait_response(b'+QIURC: "dnsgip"', timeout=timeout) # type:bytes
            if response is None:
                return None
            fields = str(response, 'utf-8').split(',')

            if len(fields) < 4 or int(fields[1]) != 0:
                return None
            count = int(fields[2])
            ipaddrs = []
            for i in range(count):
                mv = await self.wait_response_into(b'+QIURC: "dnsgip",', response_buffer=buffer, timeout=1000)
                if mv is not None:
                    ipaddrs.append(str(mv[18:-1], 'utf-8')) # strip double-quote
            return ipaddrs
        except ValueError:
            return None

        except self.CancelledError:
            pass
        
    async def get_time(self):
        """
        Returns an 6-touple with the current date and time.
        The 6-touple has following format:
          (year, month, day, hours, minutes, seconds)
        """
        import ure as re
        response = await self.execute_command_single_response(b'AT+CCLK?', b'+CCLK:')
        response = response.decode('utf-8')
        #print('res:', response)
        re_res = re.match(r'\+CCLK: "(\d\d)/(\d\d)/(\d\d),(\d\d):(\d\d):(\d\d)\+(\d\d)"', response)
        if re_res is None:
            raise LTEModuleError('Failed to get time.')
        return (int(re_res.group(1))+2000,  # year
                int(re_res.group(2)),  # month
                int(re_res.group(3)),  # day
                int(re_res.group(4)),  # hours
                int(re_res.group(5)),  # minutes
                int(re_res.group(6)))  # seconds

    async def socket_open(self, host, port, socket_type, timeout=30*1000):
        """
        Open a new socket to communicate with a host.

        :param str host:        An address of the remote host.  
        :param int port:        Port number of the remote host.
        :param int socket_type: Socket type. SOCKET_TCP or SOCKET_UDP
        :return:                Connection ID of opened socket if success. Otherwise raise LTEModuleError.
        :raises LTEModuleError: If the communication module failed to open a new socket.
        """
        assert(host is not None)
        assert(port is not None and 0 <= port and port <= 65535)
        if socket_type == LTEModule.SOCKET_TCP:
            socket_type_name = 'TCP'
        elif socket_type == LTEModule.SOCKET_UDP:
            socket_type_name = 'UDP'
        else:
            socket_type_name = None
        assert(socket_type_name is not None)

        await self.__process_remaining_urcs(timeout=timeout)

        buffer = bytearray(1024)

        success, responses = await self.execute_command(b'AT+QISTATE?', buffer, timeout=timeout)
        if not success:
            raise LTEModuleError('Failed to get socket status')
        connect_id_in_use = set()
        for response in responses:
            if len(response) < 10 or response[:10] != b'+QISTATE: ': continue
            s = str(bytes(response[10:]), 'utf-8')
            params = s.split(',',1)
            connect_id = int(params[0])
            connect_id_in_use.add(connect_id)

        new_connect_id = None
        for connect_id in range(LTEModule.MAX_CONNECT_ID):
            if connect_id not in connect_id_in_use and connect_id not in self.__connections:
                new_connect_id = connect_id
                break
        if new_connect_id is None:
            raise LTEModuleError('No connection resources available.')

        # Open socket.
        command = bytes('AT+QIOPEN=1,{0},"{1}","{2}",{3},0,0'.format(connect_id, socket_type_name, host, port), 'utf-8')
        if not await self.write_command_wait(command, b'OK', timeout=timeout):
            raise LTEModuleError('Failed to open socket. OK')
        response = await self.wait_response(bytes('+QIOPEN: {0},'.format(connect_id), 'utf-8'), timeout=timeout)
        if response is None:
            raise LTEModuleError('Failed to open socket. QIOPEN')
        error = str(response, 'utf-8').split(',')[1]
        if error != '0':
            raise LTEModuleError('Failed to open socket. error={0}'.format(error))

        self.__connections.append(connect_id)
        return connect_id

    async def socket_send(self, connect_id, data, offset=0, length=None, timeout=None):
        """Send a packet to destination."""
        assert(0 <= connect_id and connect_id <= LTEModule.MAX_CONNECT_ID)
        await self.__process_remaining_urcs(timeout=timeout)
        if connect_id not in self.__connections:
            return False
        
        length = len(data) if length is None else length
        if length == 0:
            return True
        assert(length <= LTEModule.MAX_SOCKET_DATA_SIZE)

        command = bytes('AT+QISEND={0},{1}'.format(connect_id, length), 'utf-8')
        self.write_command(command)
        if not await self.wait_prompt(b'> ', timeout=timeout):
            return False
        mv = memoryview(data)
        self.__uart.write(mv[offset:offset+length])
        return await self.wait_response(b'SEND OK', timeout=timeout) is not None
    
    async def socket_receive(self, connect_id, buffer, offset=0, length=None, timeout=None):
        assert(0 <= connect_id and connect_id <= LTEModule.MAX_CONNECT_ID)
        await self.__process_remaining_urcs(timeout=timeout)
        if connect_id not in self.__connections:
            return False
        
        length = len(buffer) if length is None else length
        if length == 0:
            return 0
        assert(length <= LTEModule.MAX_SOCKET_DATA_SIZE)

        command = bytes('AT+QIRD={0},{1}'.format(connect_id,length), 'utf-8')
        self.write_command(command)
        response = await self.wait_response(b'+QIRD: ', timeout=timeout)
        if response is None:
            return None
        actual_length = int(str(response[7:], 'utf-8'))
        if actual_length == 0:
            return 0 if await self.wait_response(b'OK', timeout=timeout) is not None else None
        mv = memoryview(buffer)
        bytes_read = self.__uart.readinto(mv[offset:offset+length], actual_length)
        return actual_length if bytes_read == actual_length and await self.wait_response(b'OK', timeout=timeout) is not None else None
    
    async def socket_close(self, connect_id, timeout=None):
        assert(0 <= connect_id and connect_id <= LTEModule.MAX_CONNECT_ID)
        if connect_id not in self.__connections:
            return False
        command = bytes('AT+QICLOSE={0}'.format(connect_id), 'utf-8')
        await self.write_command_wait(command, expected_response=b'OK', timeout=timeout)
        self.__connections.remove(connect_id)
        return True

    def socket_is_connected(self, connect_id):
        return connect_id in self.__connections and ("closed", connect_id) not in self.__urcs

    def is_busy(self):
        return bool(self.__pin_module_status.value())

    def write(self, s):
        self.__uart.write(s)
    
    def read(self, length:int) -> bytes:
        return self.__uart.read(length)
    
    def write_command(self, command:bytes) -> None:
        self.__uart.write(command)
        self.__uart.write('\r')

    async def write_command_wait(self, command, expected_response, timeout=None):
        self.write_command(command)
        return await self.wait_response(expected_response,
                                        timeout=timeout) is not None

    async def read_response_into(self, buffer, offset=0, timeout=None):
        while True:
            length = await self.__read_response_into(buffer=buffer, offset=offset, timeout=timeout)
            mv = memoryview(buffer)
            if (length is not None and
                length >= 8 and mv[0:8] == b"+QIURC: "):
                if length > 17 and mv[8:16] == b'"closed"':
                    connect_id = int(str(mv[17:length], 'utf-8'))
                    self.__urcs.append( ("closed", connect_id) )
                    continue
            
            return length

    async def __read_response_into(self, buffer, offset=0, timeout=None):
        buffer_length = len(buffer)
        response_length = 0
        state = 0
        start_time_ms = ticks_ms()
        while True:
            c = self.__uart.readchar()
            if c < 0:
                if (timeout is not None and
                    ticks_diff(ticks_ms(), start_time_ms) >= timeout):
                    return None
                try:
                    await self.sleep_ms(1)
                except self.CancelledError:
                    return None
                continue
            
            if state == 0 and c == LTEModule.CR:
                state = 1
            elif state == 1 and c == LTEModule.LF:
                state = 2
            elif state == 1 and c == LTEModule.CR:
                state = 1
            elif state == 1 and c != LTEModule.LF:
                response_length = 0
                state = 0
            elif state == 2 and c == LTEModule.CR:
                if response_length == 0:
                    state = 1   # Maybe there is another corresponding CR-LF followed by actual response data. So we have to return to state 1.
                else:
                    state = 4
            elif state == 2 and c != LTEModule.CR:
                buffer[offset+response_length] = c
                response_length += 1
                if offset+response_length == buffer_length:
                    state = 3
            elif state == 3 and c == LTEModule.CR:
                state = 4
            elif state == 4 and c == LTEModule.LF:
                return response_length
    
    async def __process_remaining_urcs(self, timeout=None):
        for urc_type, urc_params in self.__urcs:
            if urc_type == 'closed':
                await self.socket_close(urc_params, timeout=timeout)
        self.__urcs.clear()
    
    async def wait_response(self, expected_response, max_response_size=1024, timeout=None):
        response = bytearray(max_response_size)
        expected_length = len(expected_response)
        while True:
            length = await self.read_response_into(response, timeout=timeout)
            if length is None: return None
            if length >= expected_length and response[:expected_length] == expected_response:
                return response[:length]
    
    async def wait_response_into(self, expected_response, response_buffer, timeout=None):
        expected_length = len(expected_response)
        mv = memoryview(response_buffer)
        while True:
            length = await self.read_response_into(response_buffer, timeout=timeout)
            if length is None: return None
            if length >= expected_length and mv[:expected_length] == expected_response:
                return mv[:length]

    async def wait_prompt(self, expected_prompt, timeout=None):
        prompt_length = len(expected_prompt)
        index = 0
        start_time_ms = ticks_ms()
    
        while True:
            c = self.__uart.readchar()
            if c < 0:
                if ticks_diff(ticks_ms(), start_time_ms) > timeout:
                    return False
                await self.sleep_ms(1)
                continue
            if expected_prompt[index] == c:
                index += 1
                if index == prompt_length:
                    return True
            else:
                index = 0
        
    async def execute_command(self, command, response_buffer, index=0, expected_response_predicate=None, expected_response_list=[b'OK'], timeout=None):
        assert expected_response_predicate is not None or expected_response_list is not None
        if expected_response_predicate is None:
            expected_response_predicate = lambda mv: mv in expected_response_list 
        self.write_command(command)
        buffer_length = len(response_buffer)
        responses = []
        mv = memoryview(response_buffer)
        while True:
            length = await self.read_response_into(response_buffer, index, timeout=timeout)
            if length is None:
                return (False, responses)
            response = mv[index:index+length]
            responses.append(response)
            if expected_response_predicate(response):
                return (True, responses)
            index += length

    async def execute_command_single_response(self, command, starts_with=None, timeout=None):
        buffer = bytearray(1024)
        result, responses = await self.execute_command(command,
                                                       buffer,
                                                       timeout=timeout)
        if not result: return None
        starts_with_length = len(starts_with) if starts_with is not None else 0

        for response in responses:
            if starts_with_length == 0 and len(response) > 0:
                response = bytes(response)
                return response
            if starts_with_length > 0 and len(response) >= starts_with_length and response[:starts_with_length] == starts_with:
                response = bytes(response)
                return response
        return None

wiolte = WioLTE()
