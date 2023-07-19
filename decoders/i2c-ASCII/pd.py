##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2010-2016 Uwe Hermann <uwe@hermann-uwe.de>
##
##
##  MODIFIED to give ASCII charecter set.
##  Modified by: Tim Jackson.1960.
##  https://www.timsnet.co.uk/
##
##  This Is a copy of the i2c decoder with some addition to give an output with the actual ASCII carecters.
##  Lines:  243 to 275 and 79 to 86.
##
##  I prefire it as a seperate decoder so both can be added to the session.
##  The way I use PulseView with I2C is I have the normal i2c decoder, with this decoder also.
##  That way you can see the HEX code also the ASCII charector.
##
##  I should have called it ASCII-127
##  It only converts HEX 0 to 127, after that it shows HEX values.
##
##
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##
##
##

# TODO: Look into arbitration, collision detection, clock synchronisation, etc.
# TODO: Implement support for inverting SDA/SCL levels (0->1 and 1->0).
# TODO: Implement support for detecting various bus errors.

import sigrokdecode as srd

'''
OUTPUT_PYTHON format:

Packet:
[<ptype>, <pdata>]

<ptype>:
 - 'START' (START condition)
 - 'START REPEAT' (Repeated START condition)
 - 'ADDRESS READ' (Slave address, read)
 - 'ADDRESS WRITE' (Slave address, write)
 - 'DATA READ' (Data, read)
 - 'DATA WRITE' (Data, write)
 - 'STOP' (STOP condition)
 - 'ACK' (ACK bit)
 - 'NACK' (NACK bit)
 - 'BITS' (<pdata>: list of data/address bits and their ss/es numbers)

<pdata> is the data or address byte associated with the 'ADDRESS*' and 'DATA*'
command. Slave addresses do not include bit 0 (the READ/WRITE indication bit).
For example, a slave address field could be 0x51 (instead of 0xa2).
For 'START', 'START REPEAT', 'STOP', 'ACK', and 'NACK' <pdata> is None.
'''

# CMD: [annotation-type-index, long annotation, short annotation]
proto = {
    'START':           [0, 'Start',         'S'],
    'START REPEAT':    [1, 'Start repeat',  'Sr'],
    'STOP':            [2, 'Stop',          'P'],
    'ACK':             [3, 'ACK',           'A'],
    'NACK':            [4, 'NACK',          'N'],
    'BIT':             [5, 'Bit',           'B'],
    'ADDRESS READ':    [6, 'Address read',  'AR'],
    'ADDRESS WRITE':   [7, 'Address write', 'AW'],
    'DATA READ':       [8, 'Read HEX',     'RH'],
    'DATA WRITE':      [9, 'Write HEX',    'WH'],
}

###     <CHANGED

protoASCII = {
    'DATA READ':       [8, 'Read ASCII',     'RA'],
    'DATA WRITE':      [9, 'Write ASCII',    'WA'],
}

###     CHANGED>

class Decoder(srd.Decoder):
    api_version = 3
    id = 'i2c-ASCII'
    name = 'I²C-ASCII'
    longname = 'Inter-Integrated Circuit with ASCII charecters output'
    desc = 'Two-wire, multi-master, serial bus.'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = ['i2c']
    tags = ['Embedded/industrial']
    channels = (
        {'id': 'scl', 'name': 'SCL', 'desc': 'Serial clock line'},
        {'id': 'sda', 'name': 'SDA', 'desc': 'Serial data line'},
    )
    options = (
        {'id': 'address_format', 'desc': 'Displayed slave address format',
            'default': 'shifted', 'values': ('shifted', 'unshifted')},
    )
    annotations = (
        ('start', 'Start condition'),
        ('repeat-start', 'Repeat start condition'),
        ('stop', 'Stop condition'),
        ('ack', 'ACK'),
        ('nack', 'NACK'),
        ('bit', 'Data/address bit'),
        ('address-read', 'Address read'),
        ('address-write', 'Address write'),
        ('data-read', 'Data read'),
        ('data-write', 'Data write'),
        ('warning', 'Warning'),
    )
    annotation_rows = (
        ('bits', 'Bits', (5,)),
        ('addr-data', 'Address/data', (0, 1, 2, 3, 4, 6, 7, 8, 9)),
        ('warnings', 'Warnings', (10,)),
    )
    binary = (
        ('address-read', 'Address read'),
        ('address-write', 'Address write'),
        ('data-read', 'Data read'),
        ('data-write', 'Data write'),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None
        self.ss = self.es = self.ss_byte = -1
        self.bitcount = 0
        self.databyte = 0
        self.wr = -1
        self.is_repeat_start = 0
        self.state = 'FIND START'
        self.pdu_start = None
        self.pdu_bits = 0
        self.bits = []

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def start(self):
        self.out_python = self.register(srd.OUTPUT_PYTHON)
        self.out_ann = self.register(srd.OUTPUT_ANN)
        self.out_binary = self.register(srd.OUTPUT_BINARY)
        self.out_bitrate = self.register(srd.OUTPUT_META,
                meta=(int, 'Bitrate', 'Bitrate from Start bit to Stop bit'))

    def putx(self, data):
        self.put(self.ss, self.es, self.out_ann, data)

    def putp(self, data):
        self.put(self.ss, self.es, self.out_python, data)

    def putb(self, data):
        self.put(self.ss, self.es, self.out_binary, data)

    def handle_start(self, pins):
        self.ss, self.es = self.samplenum, self.samplenum
        self.pdu_start = self.samplenum
        self.pdu_bits = 0
        cmd = 'START REPEAT' if (self.is_repeat_start == 1) else 'START'
        self.putp([cmd, None])
        self.putx([proto[cmd][0], proto[cmd][1:]])
        self.state = 'FIND ADDRESS'
        self.bitcount = self.databyte = 0
        self.is_repeat_start = 1
        self.wr = -1
        self.bits = []

    # Gather 8 bits of data plus the ACK/NACK bit.
    def handle_address_or_data(self, pins):
        scl, sda = pins
        self.pdu_bits += 1

        # Address and data are transmitted MSB-first.
        self.databyte <<= 1
        self.databyte |= sda

        # Remember the start of the first data/address bit.
        if self.bitcount == 0:
            self.ss_byte = self.samplenum

        # Store individual bits and their start/end samplenumbers.
        # In the list, index 0 represents the LSB (I²C transmits MSB-first).
        self.bits.insert(0, [sda, self.samplenum, self.samplenum])
        if self.bitcount > 0:
            self.bits[1][2] = self.samplenum
        if self.bitcount == 7:
            self.bitwidth = self.bits[1][2] - self.bits[2][2]
            self.bits[0][2] += self.bitwidth

        # Return if we haven't collected all 8 + 1 bits, yet.
        if self.bitcount < 7:
            self.bitcount += 1
            return

        d = self.databyte
        if self.state == 'FIND ADDRESS':
            # The READ/WRITE bit is only in address bytes, not data bytes.
            self.wr = 0 if (self.databyte & 1) else 1
            if self.options['address_format'] == 'shifted':
                d = d >> 1

        bin_class = -1
        if self.state == 'FIND ADDRESS' and self.wr == 1:
            cmd = 'ADDRESS WRITE'
            bin_class = 1
        elif self.state == 'FIND ADDRESS' and self.wr == 0:
            cmd = 'ADDRESS READ'
            bin_class = 0
        elif self.state == 'FIND DATA' and self.wr == 1:
            cmd = 'DATA WRITE'
            bin_class = 3
        elif self.state == 'FIND DATA' and self.wr == 0:
            cmd = 'DATA READ'
            bin_class = 2

        self.ss, self.es = self.ss_byte, self.samplenum + self.bitwidth

        self.putp(['BITS', self.bits])
        self.putp([cmd, d])

        self.putb([bin_class, bytes([d])])

        for bit in self.bits:
            self.put(bit[1], bit[2], self.out_ann, [5, ['%d' % bit[0]]])

        if cmd.startswith('ADDRESS'):
            self.ss, self.es = self.samplenum, self.samplenum + self.bitwidth
            w = ['Write', 'Wr', 'W'] if self.wr else ['Read', 'Rd', 'R']
            self.putx([proto[cmd][0], w])
            self.ss, self.es = self.ss_byte, self.samplenum

###     <CHANGED

# Define an array of text descriptions for invisible HEX codes
        invisible_hex_descriptions = ['NULL', 'SOH', 'STX', 'ETX', 'EOT', 'ENQ', 'ACK', 'BEL',
                                      'BS', 'HT', 'LF', 'VT', 'FF', 'CR', 'SO', 'SI',
                                      'DLE', 'DC1', 'DC2', 'DC3', 'DC4', 'NAK', 'SYN', 'ETB',
                                      'CAN', 'EM', 'SUB', 'ESC', 'FS', 'GS', 'RS', 'US']

        if cmd.startswith('DATA') and d < 0x80:

            temp_hex = '%02X' % d

            # Check if the value of temp_hex is an invisible HEX code
            if temp_hex == '20':
                # Change the output to display "Write char: SPACE"
                self.putx([protoASCII[cmd][0], ['%s: %s' % (protoASCII[cmd][1], 'SPACE'),'%s: %s' % (protoASCII[cmd][2], 'SPACE'),'%s' % 'SPACE']])
            elif temp_hex == '7F':
                # Change the output to display "Write char: DEL"
                self.putx([protoASCII[cmd][0], ['%s: %s' % (protoASCII[cmd][1], 'DEL'),'%s: %s' % (protoASCII[cmd][2], 'DEL'),'%s' % 'DEL']])
            elif temp_hex in ['%02X' % i for i in range(0x00, 0x1F + 1)]:
                # Change the output to display the text description for the invisible HEX code
                description_index = int(temp_hex, 16)
                description = invisible_hex_descriptions[description_index]
                self.putx([protoASCII[cmd][0], ['%s: %s' % (protoASCII[cmd][1], description),'%s: %s' % (protoASCII[cmd][2], description),'%s' % description]])
            else:
                # Keep the original output
                out = bytearray.fromhex(temp_hex).decode()
                self.putx([protoASCII[cmd][0], ['%s: %s' % (protoASCII[cmd][1], out),'%s: %s' % (protoASCII[cmd][2], out),'%s' % out]])

        else:
            self.putx([proto[cmd][0], ['%s: %02X' % (proto[cmd][1], d),'%s: %02X' % (proto[cmd][2], d),'%02X' % d]])

###     CHANGED>

        # Done with this packet.
        self.bitcount = self.databyte = 0
        self.bits = []
        self.state = 'FIND ACK'

    def get_ack(self, pins):
        scl, sda = pins
        self.ss, self.es = self.samplenum, self.samplenum + self.bitwidth
        cmd = 'NACK' if (sda == 1) else 'ACK'
        self.putp([cmd, None])
        self.putx([proto[cmd][0], proto[cmd][1:]])
        # There could be multiple data bytes in a row, so either find
        # another data byte or a STOP condition next.
        self.state = 'FIND DATA'

    def handle_stop(self, pins):
        # Meta bitrate
        if self.samplerate:
            elapsed = 1 / float(self.samplerate) * (self.samplenum - self.pdu_start + 1)
            bitrate = int(1 / elapsed * self.pdu_bits)
            self.put(self.ss_byte, self.samplenum, self.out_bitrate, bitrate)

        cmd = 'STOP'
        self.ss, self.es = self.samplenum, self.samplenum
        self.putp([cmd, None])
        self.putx([proto[cmd][0], proto[cmd][1:]])
        self.state = 'FIND START'
        self.is_repeat_start = 0
        self.wr = -1
        self.bits = []

    def decode(self):
        while True:
            # State machine.
            if self.state == 'FIND START':
                # Wait for a START condition (S): SCL = high, SDA = falling.
                self.handle_start(self.wait({0: 'h', 1: 'f'}))
            elif self.state == 'FIND ADDRESS':
                # Wait for a data bit: SCL = rising.
                self.handle_address_or_data(self.wait({0: 'r'}))
            elif self.state == 'FIND DATA':
                # Wait for any of the following conditions (or combinations):
                #  a) Data sampling of receiver: SCL = rising, and/or
                #  b) START condition (S): SCL = high, SDA = falling, and/or
                #  c) STOP condition (P): SCL = high, SDA = rising
                pins = self.wait([{0: 'r'}, {0: 'h', 1: 'f'}, {0: 'h', 1: 'r'}])

                # Check which of the condition(s) matched and handle them.
                if self.matched[0]:
                    self.handle_address_or_data(pins)
                elif self.matched[1]:
                    self.handle_start(pins)
                elif self.matched[2]:
                    self.handle_stop(pins)
            elif self.state == 'FIND ACK':
                # Wait for a data/ack bit: SCL = rising.
                self.get_ack(self.wait({0: 'r'}))
