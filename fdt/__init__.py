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

import os

from .node import Node
from .prop import Property, PropBytes, PropWords, PropStrings
from .head import Header, DTB_BEGIN_NODE, DTB_END_NODE, DTB_NOP, DTB_PROP, DTB_END
from .misc import strip_comments, split_to_lines, get_version_info, extract_string

__author__  = "Martin Olejar"
__contact__ = "martin.olejar@gmail.com"
__version__ = "0.1.0"
__license__ = "Apache 2.0"
__status__  = "Development"
__all__     = [
    # FDT Classes
    'FDT',
    'Node',
    'Header',
    'PropBytes',
    'PropWords',
    'PropStrings',
    # core methods
    'parse_dts',
    'parse_dtb'
]


class FDT(object):
    """ Flattened Device Tree Class """

    def __init__(self):
        self.header = Header()
        self.entries = []
        self.rootnode = None

    def info(self):
        pass

    def diff(self, target_fdt):
        # prepare local hash table
        local_table = {}
        for i in self.walk():
            local_table[i[0]] = i[1]
        # prepare target table
        target_table = {}
        for i in target_fdt.walk():
            target_table[i[0]] = i[1]
        # 1.st phase of creating diff table
        # by comparing 'local_table' against 'target_table'.
        # if key is present in both tables, drop it from 
        # 'target_table' to simplify second phase, so it 
        #  will eventualy evaluate only uncompared items. 
        diff_table = {}
        for local_key in local_table:
            local_obj = local_table[local_key]
            if local_key in target_table:
                # objects are the same, drop from 'target_table'
                target_obj = target_table[local_key]
                if target_obj == local_obj:
                    del target_table[local_key]
                # objects are not equal, store both objects, drop from 'target_table'
                else:
                    del target_table[local_key]
                    diff_table[local_key] = {
                        'status':   'different',
                        'local':    local_obj,
                        'target':   target_obj
                    }
            else:
                # 'local_key' is not present in 'target_table'
                diff_table[local_key] = {
                    'status':   'missing',
                    'local':    local_obj
                }
        # 2.nd phase, iterate over items that exists only in 'target_table'
        # if both fdt files are the same, this loop won't be executed
        for target_key in target_table:
            target_obj = target_table[target_key]
            diff_table[target_key] = {
                'status':   'added',
                'target':    target_obj
            }
        return diff_table

    def walk(self):
        todo_stack = []
        condition = True
        tmp_object = self.rootnode
        tmp_object.basepath = ''
        while True:
            basepath = tmp_object.basepath
            if isinstance(tmp_object, Node):
                # push current childs on 'todo' stack
                if tmp_object.nodes:
                    for n in tmp_object.nodes:
                        n.basepath = basepath + '/' + tmp_object.name
                        todo_stack.append(n)
                # push current properties on 'todo' stack
                if tmp_object.props:
                    for n in tmp_object.props:
                        n.basepath = basepath + '/' + tmp_object.name
                        todo_stack.append(n)
                # yield if current object is an empty node
                if not tmp_object.nodes and not tmp_object.props:
                    yield (tmp_object.basepath + '/' + tmp_object.name, tmp_object)
            # yield if current object is an property
            if isinstance(tmp_object, Property):
                yield (tmp_object.basepath + '/.' + tmp_object.name, tmp_object)
            # terminate if 'todo' stack is empty
            if not todo_stack:
                break
            # take another node from 'todo' stack
            tmp_object = todo_stack.pop()

    def merge(self, fdt):
        if not isinstance(fdt, FDT):
            raise Exception("Error")
        if self.header.version is None:
            self.header = fdt.header
        else:
            if fdt.header.version is not None and \
               fdt.header.version > self.header.version:
                self.header.version = fdt.header.version
        if fdt.entries:
            for in_entry in fdt.entries:
                exist = False
                for index in range(len(self.entries)):
                    if self.entries[index]['address'] == in_entry['address']:
                        self.entries[index]['address'] = in_entry['size']
                        exist = True
                        break
                if not exist:
                    self.entries.append(in_entry)
        self.rootnode.merge(fdt.rootnode)

    def to_dts(self, tabsize=4):
        """Store FDT Object into string format (DTS)"""
        result = "/dts-v1/;\n"
        result += "// version: {}\n".format(self.header.version)
        result += "// last_comp_version: {}\n".format(self.header.last_comp_version)
        if self.header.version >= 2:
            result += "// boot_cpuid_phys: 0x{:X}\n".format(self.header.boot_cpuid_phys)
        result += '\n'
        if self.entries:
            for entry in self.entries:
                result += "/memreserve/ "
                result += "{:#x} ".format(entry['address']) if entry['address'] else "0 "
                result += "{:#x}".format(entry['size']) if entry['size'] else "0"
                result += ";\n"
        if self.rootnode is not None:
            result += self.rootnode.to_dts(tabsize)
        return result

    def to_dtb(self, version=None, last_comp_version=None, boot_cpuid_phys=None):
        """Export FDT Object into Binary Blob format (DTB)"""
        if self.rootnode is None:
            return None

        from struct import pack

        if version is not None:
            self.header.version = version
        if last_comp_version is not None:
            self.header.last_comp_version = last_comp_version
        if boot_cpuid_phys is not None:
            self.header.boot_cpuid_phys = boot_cpuid_phys
        if self.header.version is None:
            raise Exception("DTB Version must be specified !")

        blob_entries = bytes()
        if self.entries:
            for entry in self.entries:
                blob_entries += pack('>QQ', entry['address'], entry['size'])
        blob_entries += pack('>QQ', 0, 0)
        blob_data_start = self.header.size + len(blob_entries)
        (blob_data, blob_strings, data_pos) = self.rootnode.to_dtb('', blob_data_start, self.header.version)
        blob_data += pack('>I', DTB_END)
        self.header.size_dt_strings = len(blob_strings)
        self.header.size_dt_struct = len(blob_data)
        self.header.off_mem_rsvmap = self.header.size
        self.header.off_dt_struct = blob_data_start
        self.header.off_dt_strings = blob_data_start + len(blob_data)
        self.header.total_size = blob_data_start + len(blob_data) + len(blob_strings)
        blob_header = self.header.export()
        return blob_header + blob_entries + blob_data + blob_strings.encode('ascii')


def parse_dts(text, root_dir=''):
    """Parse DTS text file and create FDT Object"""
    ver = get_version_info(text)
    text = strip_comments(text)
    dts_lines = split_to_lines(text)
    fdt_obj = FDT()
    if 'version' in ver:
        fdt_obj.header.version = ver['version']
    if 'last_comp_version' in ver:
        fdt_obj.header.last_comp_version = ver['last_comp_version']
    if 'boot_cpuid_phys' in ver:
        fdt_obj.header.boot_cpuid_phys = ver['boot_cpuid_phys']
    # parse entries
    fdt_obj.entries = []
    for line in dts_lines:
        if line.endswith('{'):
            break
        if line.startswith('/memreserve/'):
            line = line.strip(';')
            line = line.split()
            if len(line) != 3 :
                raise Exception()
            fdt_obj.entries.append({'address': int(line[1], 0), 'size': int(line[2], 0)})
    # parse nodes
    curnode = None
    fdt_obj.rootnode = None
    for line in dts_lines:
        if line.endswith('{'):
            # start node
            node_name = line.split()[0]
            new_node = Node(node_name)
            if fdt_obj.rootnode is None:
                fdt_obj.rootnode = new_node
            if curnode is not None:
                curnode.append(new_node)
                new_node.parent = curnode
            curnode = new_node
        elif line.endswith('}'):
            # end node
            if curnode is not None:
                curnode = curnode.parent
        else:
            # properties
            if line.find('=') == -1:
                prop_name = line
                prop_obj = Property(prop_name)
            else:
                line = line.split('=', maxsplit=1)
                prop_name = line[0].rstrip(' ')
                prop_value = line[1].lstrip(' ')
                if prop_value.startswith('<'):
                    prop_obj = PropWords(prop_name)
                    prop_value = prop_value.replace('<', '').replace('>', '')
                    for prop in prop_value.split():
                        prop_obj.append(int(prop, 0))
                elif prop_value.startswith('['):
                    prop_obj = PropBytes(prop_name)
                    prop_value = prop_value.replace('[', '').replace(']', '')
                    for prop in prop_value.split():
                        prop_obj.append(int(prop, 16))
                elif prop_value.startswith('/incbin/'):
                    prop_value = prop_value.replace('/incbin/("', '').replace('")', '')
                    prop_value = prop_value.split(',')
                    file_path  = os.path.join(root_dir, prop_value[0].strip())
                    file_offset = int(prop_value.strip(), 0) if len(prop_value) > 1 else 0
                    file_size = int(prop_value.strip(), 0) if len(prop_value) > 2 else 0
                    if file_path is None or not os.path.exists(file_path):
                        raise Exception("File path doesn't exist: {}".format(file_path))
                    with open(file_path, "rb") as f:
                        f.seek(file_offset)
                        data = f.read(file_size) if file_size > 0 else f.read()
                    prop_obj = PropBytes(prop_name, data)
                elif prop_value.startswith('/plugin/'):
                    raise NotImplementedError("Not implemented property value: /plugin/")
                elif prop_value.startswith('/bits/'):
                    raise NotImplementedError("Not implemented property value: /bits/")
                else:
                    prop_obj = PropStrings(prop_name)
                    for prop in prop_value.split('",'):
                        prop = prop.replace('"', "")
                        prop = prop.strip()
                        prop_obj.append(prop)
            if curnode is not None:
                curnode.append(prop_obj)

    return fdt_obj


def parse_dtb(data):
    """ Parse FDT Binary Blob and create FDT Object """
    from struct import unpack_from

    fdt_obj = FDT()
    # parse header
    fdt_obj.header = Header.parse(data)
    # parse entries
    offset = fdt_obj.header.off_mem_rsvmap
    aa = data[offset:]
    while True:
        entrie = dict(zip(('address', 'size'), unpack_from(">QQ", data, offset)))
        offset += 16
        if entrie['address'] == 0 and entrie['size'] == 0:
            break
        fdt_obj.entries.append(entrie)
    # parse nodes
    curnode = None
    offset = fdt_obj.header.off_dt_struct
    while True:
        if len(data) < (offset + 4):
            raise Exception("Error ...")

        tag = unpack_from(">I", data, offset)[0]
        offset += 4
        if tag == DTB_BEGIN_NODE:
            node_name = extract_string(data, offset)
            offset = ((offset + len(node_name) + 4) & ~3)
            if not node_name: node_name = '/'
            new_node = Node(node_name)
            if fdt_obj.rootnode is None:
                fdt_obj.rootnode = new_node
            if curnode is not None:
                curnode.append(new_node)
                new_node.parent = curnode
            curnode = new_node
        elif tag == DTB_END_NODE:
            if curnode is not None:
                curnode = curnode.parent
        elif tag == DTB_PROP:
            prop_size, prop_string_pos, = unpack_from(">II", data, offset)
            prop_start = offset + 8
            if fdt_obj.header.version < 16 and prop_size >= 8:
                prop_start = ((prop_start + 7) & ~0x7)
            prop_name = extract_string(data, fdt_obj.header.off_dt_strings + prop_string_pos)
            prop_raw_value = data[prop_start: prop_start + prop_size]
            offset = prop_start + prop_size
            offset = ((offset + 3) & ~0x3)
            if curnode is not None:
                curnode.append(Property.create(prop_name, prop_raw_value))
        elif tag == DTB_END:
            break
        else:
            raise Exception("Unknown Tag: {}".format(tag))

    return fdt_obj



