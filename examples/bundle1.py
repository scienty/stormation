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

import os, sys, logging
from functools import partial
from cfn.cfn_bundle import CFBundle

here = os.path.abspath(os.path.dirname(__file__))
get_path = partial(os.path.join, here)

def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('boto3').setLevel(logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(console)

    # Optional, name of the aws profile to use for credentials, overrides the one from bundle1.yaml
    profile = 'my-aws-profile'

    yaml_file = get_path('bundle1.yaml')
    this = CFBundle(yaml_file, profile=profile)

    #this.check('iam')
    this.check('network')
    this.merge()
    # this.delete()
    # print(json.dumps(this.change_set('prakash-stack-iam')))
    #this.stack_map['cfntest-subnets'].apply(op=CFNStack.OP_DELETE,strict=False, wait=True)
    #this.stack_map['cfntest-subnets'].apply(op=CFNStack.OP_CREATE, wait=True)

if __name__ == '__main__':
    main()