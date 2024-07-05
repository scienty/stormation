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

import os
import importlib.util


def importFromURI(uri, absl=False):
    if not absl:
        uri = os.path.normpath(os.path.join(os.path.dirname(__file__), uri))
    path, fname = os.path.split(uri)
    mname, ext = os.path.splitext(fname)

    no_ext = os.path.join(path, mname)

    mod_path = None
    if os.path.exists(no_ext + '.pyc'):
        mod_path = no_ext + '.pyc'
    elif os.path.exists(no_ext + '.py'):
        mod_path = no_ext + '.py'
    else:
        return None

    spec = importlib.util.spec_from_file_location(mname, mod_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
