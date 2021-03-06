# Copyright 2017 Martin Olejar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from struct import unpack, pack
from string import printable

from .head import DTB_PROP
from .misc import is_string, line_offset


class Property(object):

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, str):
            raise ValueError("The value must be a string type !")
        if not all(c in printable for c in value):
            raise ValueError("The value must contain just printable chars !")
        self._name = value

    @property
    def basepath(self):
        return self._basepath

    @basepath.setter
    def basepath(self, value):
        self._basepath = value

    def __init__(self, name):
        """Init with name"""
        self.name = name
        self._basepath = None

    def __str__(self):
        """String representation"""
        return "{}".format(self.name)

    def __getitem__(self, value):
        """Returns No Items"""
        return None

    def __ne__(self, prop):
        """Check property inequality """
        return not self.__eq__(prop)

    def __eq__(self, prop):
        """Check properties are the same (same names) """
        if not isinstance(prop, Property):
            return False
        if self.name != prop.name:
            return False
        return True

    def to_dts(self, tabsize=4, depth=0):
        """Get dts string representation"""
        return line_offset(tabsize, depth, '{};\n'.format(self.name))

    def to_dtb(self, strings, pos=0, version=17):
        """Get blob representation"""
        strpos = strings.find(self.name + '\0')
        if strpos < 0:
            strpos = len(strings)
            strings += self.name + '\0'
        pos += 12
        return pack('>III', DTB_PROP, 0, strpos), strings, pos

    @classmethod
    def create(cls, name, raw_value):
        """ Instantiate property with raw value type """
        if is_string(raw_value):
            obj = PropStrings(name)
            # Extract strings from raw value
            for st in raw_value.decode('ascii').split('\0'):
                if len(st): obj.append(st)
            return obj

        elif len(raw_value) and len(raw_value) % 4 == 0:
            obj = PropWords(name)
            # Extract words from raw value
            for i in range(0, len(raw_value), 4):
                obj.append(unpack(">I", raw_value[i:i + 4])[0])
            return obj

        elif len(raw_value) and len(raw_value):
            return PropBytes(name, raw_value)

        else:
            return cls(name)


class PropStrings(Property):
    """Property with strings as value"""

    def __init__(self, name, strings=None):
        """Init with strings"""
        super().__init__(name)
        self.data = [] if strings is None else strings

    def __str__(self):
        """String representation"""
        return "{} = {}".format(self.name, self.data)

    def __len__(self):
        """Get strings count"""
        return len(self.data)

    def __getitem__(self, index):
        """Get strings, returns a string"""
        return self.data[index]

    def __eq__(self, prop):
        """Check properties are the same (same values)"""
        if not isinstance(prop, PropStrings):
            return False
        if self.name != prop.name:
            return False
        if len(self) != len(prop):
            return False
        for index in range(len(self)):
            if self.data[index] != prop[index]:
                return False
        return True

    def append(self, value):
        if not isinstance(value, str):
            raise TypeError("Invalid object type")
        if len(value) == 0:
            raise ValueError("Invalid strings value")
        if not all(c in printable or c in ('\r', '\n') for c in value):
            raise ValueError("Invalid chars in strings value")
        self.data.append(value)

    def pop(self, index):
        assert 0 <= index < len(self.data)
        return self.data.pop(index)

    def clear(self):
        self.data.clear()

    def to_dts(self, tabsize=4, depth=0):
        """Get DTS representation"""
        result  = line_offset(tabsize, depth, self.name)
        result += ' = "'
        result += '", "'.join(self.data)
        result += '";\n'
        return result

    def to_dtb(self, strings, pos=0, version=17):
        """Get DTB representation"""
        blob = pack('')
        for chars in self.data:
            blob += chars.encode('ascii') + pack('b', 0)
        blob_len = len(blob)
        if version < 16 and (pos + 12) % 8 != 0:
            blob = pack('b', 0) * (8 - ((pos + 12) % 8)) + blob
        if blob_len % 4:
            blob += pack('b', 0) * (4 - (blob_len % 4))
        strpos = strings.find(self.name + '\0')
        if strpos < 0:
            strpos = len(strings)
            strings += self.name + '\0'
        blob = pack('>III', DTB_PROP, blob_len, strpos) + blob
        pos += len(blob)
        return (blob, strings, pos)


class PropWords(Property):
    """Property with words as value"""

    def __init__(self, name, words=None, word_size=32):
        """Init with words"""
        super().__init__(name)
        self.data = [] if words is None else words
        self.word_size = word_size

    def __str__(self):
        """String representation"""
        return "{} = Words: {}".format(self.name, self.data)

    def __getitem__(self, index):
        """Get words, returns a word integer"""
        return self.data[index]

    def __len__(self):
        """Get words count"""
        return len(self.data)

    def __eq__(self, prop):
        """Check properties are the same (same values)"""
        if not isinstance(prop, PropWords):
            return False
        if self.name != prop.name:
            return False
        if len(self) != len(prop):
            return False
        for index in range(len(self)):
            if self.data[index] != prop[index]:
                return False
        return True

    def append(self, value):
        if not 0 <= value < 2**self.word_size:
            raise ValueError("Invalid word value {}, requires <0x0 - 0x{:X}>".format(value, 2**self.word_size - 1))
        self.data.append(value)

    def pop(self, index):
        assert 0 <= index < len(self.data)
        return self.data.pop(index)

    def clear(self):
        self.data.clear()

    def to_dts(self, tabsize=4, depth=0):
        """Get DTS representation"""
        result  = line_offset(tabsize, depth, self.name)
        result += ' = <'
        result += ' '.join(["0x{:X}".format(word) for word in self.data])
        result += ">;\n"
        return result

    def to_dtb(self, strings, pos=0, version=17):
        """Get DTB representation"""
        strpos = strings.find(self.name + '\0')
        if strpos < 0:
            strpos = len(strings)
            strings += self.name + '\0'
        blob  = pack('>III', DTB_PROP, len(self.data) * 4, strpos)
        for word in self.data:
            blob += pack('>I', word)
        pos  += len(blob)
        return (blob, strings, pos)


class PropBytes(Property):
    """Property with bytes as value"""

    def __init__(self, name, data=None):
        """Init with bytes"""
        super().__init__(name)
        self.data = bytearray() if data is None else bytearray(data)

    def __str__(self):
        """String representation"""
        return "{} = Bytes: {}".format(self.name, self.data)

    def __getitem__(self, index):
        """Get words, returns a word integer"""
        return self.data[index]

    def __len__(self):
        """Get words count"""
        return len(self.data)

    def __eq__(self, prop):
        """Check properties are the same (same values)"""
        if not isinstance(prop, PropBytes):
            return False
        if self.name != prop.name:
            return False
        if len(self) != len(prop):
            return False
        for index in range(len(self)):
            if self.data[index] != prop[index]:
                return False
        return True

    def append(self, value):
        if not 0 <= value <= 0xFF:
            raise ValueError("Invalid byte value {}, requires <0 - 255>".format(value))
        self.data.append(value)

    def pop(self, index):
        assert 0 <= index < len(self.data)
        return self.data.pop(index)

    def clear(self):
        self.data = bytearray()

    def to_dts(self, tabsize=4, depth=0):
        """Get DTS representation"""
        result  = line_offset(tabsize, depth, self.name)
        result += ' = ['
        result += ' '.join(["{:02X}".format(byte) for byte in self.data])
        result += '];\n'
        return result

    def to_dtb(self, strings, pos=0, version=17):
        """Get DTB representation"""
        strpos = strings.find(self.name + '\0')
        if strpos < 0:
            strpos = len(strings)
            strings += self.name + '\0'
        blob  = pack('>III', DTB_PROP, len(self.data), strpos)
        blob += bytes(self.data)
        if len(blob) % 4:
            blob += bytes([0] * (4 - (len(blob) % 4)))
        pos += len(blob)
        return (blob, strings, pos)

