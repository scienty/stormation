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

import time
import jmespath
import logging

from common.awssession import get_session
from common.exception import ClientError

LOG = logging.getLogger(__name__)


class AWSClient(object):

    def __init__(self, service_name, region_name=None, **kwargs):
        session = kwargs.get("session", None)
        if session is None:
            session = get_session(region_name, **kwargs)
        self._session = session

        self._service_name = service_name
        self._region_name = region_name
        self._kwargs = kwargs
        self._boto_client = self._session.client(service_name, region_name)
        if self._boto_client is None:
            raise ClientError("0", "Failed to connect to AWS service", "get boto client")
        if self._region_name is None:
            self._region_name = self._session.default_region

    @property
    def service_name(self):
        return self._service_name

    @property
    def region_name(self):
        return self._region_name

    @property
    def session(self):
        return self._session

    @property
    def profile(self):
        return self.session.profile

    @property
    def account_id(self):
        return self._session.account_id

    @property
    def user_id(self):
        return self._user_id

    def get_client(self, service_name, region_name=None):
        """
            return different service client with the same aws session
        :param service_name:
        :param region_name:
        :return:
        """
        return AWSClient(service_name, region_name, session=self.session)

    def call(self, op_name, query=None, **kwargs):
        """
        Make a request to a method in this client.  The response data is
        returned from this call as native Python data structures.
        This method differs from just calling the client method directly
        in the following ways:
          * It automatically handles the pagination rather than
            relying on a separate pagination method call.
          * You can pass an optional jmespath query and this query
            will be applied to the data returned from the low-level
            call.  This allows you to tailor the returned data to be
            exactly what you want.
        :type op_name: str
        :param op_name: The name of the request you wish to make.
        :type query: str
        :param query: A jmespath query that will be applied to the
            data returned by the operation prior to returning
            it to the user.
        :type kwargs: keyword arguments
        :param kwargs: Additional keyword arguments you want to pass
            to the method when making the request.
        """
        LOG.debug(kwargs)
        if query:
            query = jmespath.compile(query)
        if self._boto_client.can_paginate(op_name):
            paginator = self._boto_client.get_paginator(op_name)
            results = paginator.paginate(**kwargs)
            data = results.build_full_result()
        else:
            op = getattr(self._boto_client, op_name)
            done = False
            data = {}
            while not done:
                try:
                    data = op(**kwargs)
                    done = True
                except ClientError as e:
                    LOG.debug(e, kwargs)
                    if 'Throttling' in str(e):
                        time.sleep(1)
                    elif 'AccessDenied' in str(e):
                        raise e
                        done = True
                except Exception as e:
                    raise e
                    done = True
        if query:
            data = query.search(data)
        return data
