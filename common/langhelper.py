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
import imp


def importFromURI(uri, absl=False):
    if not absl:
        uri = os.path.normpath(os.path.join(os.path.dirname(__file__), uri))
    path, fname = os.path.split(uri)
    mname, ext = os.path.splitext(fname)

    no_ext = os.path.join(path, mname)

    if os.path.exists(no_ext + '.pyc'):
        try:
            return imp.load_compiled(mname, no_ext + '.pyc')
        except Exception as e:
            raise e
    if os.path.exists(no_ext + '.py'):
        try:
            return imp.load_source(mname, no_ext + '.py')
        except Exception as e:
            raise e

	return None
