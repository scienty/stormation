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

import logging
import boto3
import os

LOG = logging.getLogger(__name__)



class AWSSession(object):

    def __init__(self, default_region=None, profile=None, credentials=None, **kwargs):
        self._default_region = default_region
        # no aws_creds, need profile to get creds from ~/.aws/credentials
        self._profile = profile

        if credentials:
            self._session = boto3.Session(**self.credentials)
        elif profile:
            self._session = boto3.Session(profile_name=profile)  
        else:
            self._session = boto3.Session()

        self.placebo = kwargs.get('placebo')
        self.placebo_dir = kwargs.get('placebo_dir')
        self.placebo_mode = kwargs.get('placebo_mode', 'record')

        if self.placebo and self.placebo_dir:
            pill = self.placebo.attach(self._session, self.placebo_dir)
            if self.placebo_mode == 'record':
                pill.record()
            elif self.placebo_mode == 'playback':
                pill.playback()

        self._fetch_account_info()

    @property
    def default_region(self):
        return self._default_region

    @property
    def account_id(self):
        return self._account_id

    @property
    def user_id(self):
        return self._user_id

    def _fetch_account_info(self):
        client = self._session.client("sts")
        data = client.get_caller_identity()
        self._account_id = data["Account"]
        self._user_id = data["UserId"]

    def client(self, service_name, region_name=None, **kwargs):
        if region_name is None:
            region_name = self.default_region

        return self._session.client(service_name=service_name, region_name=region_name, **kwargs)

# sessions by profile
sessions = dict()


def get_session(region_name=None, profile=None, **kwargs):
    session = sessions.get(profile)
    if session is None:
        session = AWSSession(region_name, profile, **kwargs)
        sessions[profile] = session
    return session