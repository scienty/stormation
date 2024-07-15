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
import os.path
import copy
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend

'''
This file acts as plugin for pre processing security.yaml input data
The return from prepare_context will be the context for jinja rendering of cloud formation template part
'''

protocol_map = {
    'ALL': -1,
    'ICMP': 1,
    'TCP': 6,
    'UDP': 17,
    'IPv6-ICMP': 58
}

PRIVATE_KEY_EXT = "_private_key.pem"
PUBLIC_KEY_EXT = "_public_key.pem"

self_dir = os.path.dirname(os.path.abspath(__file__))

def init(stk):
    stack = stk
    print("Initializing stack " + stack.name)

def prepare_context(context):
    process_key_pairs(context)
    process_security_groups(context)

    return context

def process_key_pairs(context):
    key_pair_names = context.get('key_pair_names', [])
    for key_name in key_pair_names:
        key_file = self_dir + "/" + key_name
        if not os.path.isfile(key_file + PUBLIC_KEY_EXT):
            generate_key_pair(key_name)

        with open(key_file + PUBLIC_KEY_EXT, "r") as key_file:
            context[key_name + "_public_key"] = key_file.read()

def generate_key_pair(key_name):
    key = rsa.generate_private_key(
        backend=crypto_default_backend(),
        public_exponent=65537,
        key_size=2048
    )

    private_key = key.private_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PrivateFormat.PKCS8,
        crypto_serialization.NoEncryption()
    )

    public_key = key.public_key().public_bytes(
        crypto_serialization.Encoding.OpenSSH,
        crypto_serialization.PublicFormat.OpenSSH
    )

    key_file = self_dir + "/" + key_name
    with open(key_file + PRIVATE_KEY_EXT, "wb") as file:
        file.write(private_key);

    with open(key_file + PUBLIC_KEY_EXT, "wb") as file:
        file.write(public_key);


def process_security_groups(context):
    security_groups = context.get('security_groups', {})
    for name, security_group in security_groups.items():
        rule_list = security_group.get('rules', [])
        rule_list = _expand_security_groups(rule_list, "direction")
        rule_list = _expand_security_groups(rule_list, "protocol")
        rule_list = _expand_security_groups(rule_list, "cidr")
        rule_list = _expand_security_groups(rule_list, "v6cidr")

        ingress_rules = []
        exgress_rules = []
        for rule in rule_list:
            process_seurity_group_rule(rule)
            if rule.get('direction') == 'ingress':
                ingress_rules.append(rule)
            else:
                exgress_rules.append(rule)

        security_group['rules'] = {
            'ingress': ingress_rules,
            'egress': exgress_rules
        }

def _expand_security_groups(entries, field):
    ret_entries = []
    for entry in entries:
        field_value = entry.get(field, None)
        if field_value is None or type(field_value) is not list:
            ret_entries.append(entry)
        else:
            for item in field_value:
                copy_item = copy.deepcopy(entry)
                copy_item[field] = item
                ret_entries.append(copy_item)

    return ret_entries

def process_seurity_group_rule(rule):
    cidr = rule.get('cidr', None)
    v6cidr = rule.get('v6cidr', None)
    prefixList = rule.get('prefixList', None)
    securityGroup = rule.get('securityGroup', None)
    securityGroupOwner = rule.get('securityGroupOwner', None)

    hashKey = ""

    if cidr is not None:
        rule['cidr'] = cidr
        hashKey = cidr
    elif v6cidr is not None:
        rule['v6cidr'] = v6cidr
        hashKey += v6cidr
    elif prefixList is not None:
        rule['prefixList'] = prefixList
    elif securityGroup is not None:
        rule['securityGroup'] = securityGroup
    elif securityGroup is not None:
        rule['securityGroupOwner'] = securityGroupOwner
    else:
        raise Exception('one of the cidr, v6cidr, prefixList, securityGroup, securityGroupOwner is required for %s' % rule)

    port_range = rule.get('ports', None)
    if port_range is None:
        raise Exception('ports missing for security group rule %s' % rule)
    hashKey += str(port_range)

    ports = str(port_range).split('-')
    from_port = None
    to_port = None
    if len(ports) == 2:
        from_port = ports[0]
        to_port = ports[1]
    elif len(ports) == 1 and "all" == ports[0].lower():
        from_port = "-1"
        to_port = from_port
    elif len(ports) == 1:
        from_port = ports[0]
        to_port = from_port
    else:
        raise Exception('Invalid port range for security group rule %s' % rule)

    rule['from_port'] = from_port
    rule['to_port'] = to_port

    protocol_str = rule.get('protocol', None)
    if protocol_str is None:
        raise Exception('protocol missing for acl entry %s' % rule)

    proto_num = protocol_map.get(protocol_str.upper(), None)
    if proto_num is None:
        raise Exception('Invalid protocol %s, valid entries are %s' % (rule, protocol_map.keys()))

    rule['protocol_num'] = proto_num
    hashKey += str(proto_num)

    direction = rule.get('direction', None)
    if direction is None or direction.lower() not in ['ingress', 'egress']:
        raise Exception('Invalid direction for rule entry %s' % rule)

    rule['id'] = '{:X}'.format(hash(hashKey))
    if rule['id'].startswith("-"):
        rule['id'] = rule['id'].lstrip("-")


if __name__ == "__main__":
    print(prepare_context({"key_pair_names":["bastion"]}))