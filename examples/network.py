# Copyright Prakash Sidaraddi.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import copy

'''
This file acts as plugin for pre processing network.yaml input data
The return from prepare_context will be the context for jinja rendering of cloud formation template part
'''

protocol_map = {
    'ALL': -1,
    'ICMP': 1,
    'TCP': 6,
    'UDP': 17,
    'IPv6-ICMP': 58
}

def init(stk):
    stack = stk
    print("Initializing stack " + stack.name)

def prepare_context(context):
    subnets = context.get('subnets', {})
    for subnet_name, subnet_def in subnets.items():
        acl_list = subnet_def.get('acl', [])
        acl_list = _expand_acl_entries(acl_list, 'direction')
        acl_list = _expand_acl_entries(acl_list, 'protocol')
        acl_list = _expand_acl_entries(acl_list, 'cidr')
        acl_list = _expand_acl_entries(acl_list, 'v6cidr')
        acl_list = _expand_acl_entries(acl_list, 'ports')
        _process_acl_entries(acl_list)
        subnet_def['acl'] = acl_list

    return context


def _expand_acl_entries(entries, field):
    ret_entries = []
    for entry in entries:
        field_value = entry.get(field, None)
        if field_value is None or type(field_value) is not list:
            ret_entries.append(entry)
        else:
            for item in field_value:
                acl_copy = copy.deepcopy(entry)
                acl_copy[field] = item
                ret_entries.append(acl_copy)

    return ret_entries

def _process_acl_entries(entries):
    for entry in entries:
        cidr = entry.get('cidr', None)
        v6cidr = entry.get('v6cidr', None)

        if cidr is None and v6cidr is None:
            raise Exception('cidr missing for acl entry %s' % entry)
        if cidr is not None:
            entry['cidr'] = cidr
        if v6cidr is not None:
            entry['v6cidr'] = v6cidr

        port_range = entry.get('ports', None)
        if port_range is None:
            raise Exception('ports missing for acl entry %s' % entry)
        ports = str(port_range).split('-')
        port_from = ports[0]
        port_to = ports[1] if len(ports) > 1 else port_from
        entry['port_from'] = port_from
        entry['port_to'] = port_to

        protocol_str = entry.get('protocol', None)
        if protocol_str is None:
            raise Exception('protocol missing for acl entry %s' % entry)

        proto_num = protocol_map.get(protocol_str.upper(), None)
        if proto_num is None:
            raise Exception('Invalid protocol %s, valid entries are %s' % (entry, protocol_map.keys()))

        entry['protocol_num'] = proto_num

        direction = entry.get('direction', None)
        if direction is None or direction.lower() not in ['ingress', 'egress']:
            raise Exception('Invalid direction for acl entry %s' % entry)

        egress = False
        if direction.lower() == 'egress':
            egress = True

        entry['egress'] = egress






