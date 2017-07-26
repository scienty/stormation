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
import botocore
import logging
from common.awsclient import AWSClient

#boto.set_stream_logger('boto')
def boto_all(func, *args, **kwargs):
    """
    Iterate through all boto next_token's
    """
    resp = {}
    ret = []

    while True:
        resp = func(*args, **kwargs)
        for val in resp.values():
            if type(val) is list:
                ret.extend(val)

        if not resp.get('NextToken', None):
            break

        kwargs['NextToken'] = ret[-1].NextToken

    return ret

class StackStatus(str):
    pass


class StackSuccessStatus(StackStatus):
    pass


class StackFailStatus(StackStatus):
    pass

class StackUnknownStatus(StackStatus):
    pass


class CloudformationException(Exception):
    pass


class StackInfo(object):
    def __init__(self, aws_client, stack_name):
        self._aws_client = aws_client
        self._stack_name = stack_name
        #self.desc = self._conn.describe_stacks(StackName=stack_name)['Stacks'][0]
        self.desc = self._aws_client.call('describe_stacks', StackName=stack_name)['Stacks'][0]
        self._resources = None
        self._template = None

    def parameters(self):
        return self.desc.get('Parameters', [])

    def outputs(self):
        return self.desc.get('Outputs', [])

    def status(self):
        return self.desc['StackStatus']

    def statusFailed(self):
        return self.status().endswith('_FAILED')

    def statusCompleted(self):
        return self.status().endswith('_COMPLETE')

    def statusInProgress(self):
        return self.status().endswith('_IN_PROGRESS')

    def resources(self):
        if self._resources is None:
            self._resources = self._aws_client.call('list_stack_resources', StackName=self._stack_name, query='StackResourceSummaries')
        return self._resources

    def template(self):
        if self._template is None:
            self._template = self._aws_client.call('get_template', StackName=self._stack_name)

        return self._template['TemplateBody']




class CFNClient(object):
    # this is from http://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_Stack.html
    # boto.cloudformation.stack.StackEvent.valid_states doesn't have the full list.
    VALID_STACK_STATUSES = ['CREATE_IN_PROGRESS', 'CREATE_FAILED', 'CREATE_COMPLETE', 'ROLLBACK_IN_PROGRESS',
                            'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'DELETE_IN_PROGRESS', 'DELETE_FAILED',
                            'DELETE_COMPLETE', 'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
                            'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_FAILED',
                            'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_ROLLBACK_COMPLETE']

    # connections by region
    clients = dict()

    @staticmethod
    def get_client(region_stack_name, refresh=False, **kwargs):
        """
        Returns a CFNConnection for a region and cache it locally, optionally you can ask to refresh the cache
        :param region:
        :param refresh:
        :return:
        :rtype: CFNClient
        """
        cfn_client = CFNClient.clients.get(region_stack_name, None)
        if refresh or cfn_client is None:
            cfn_client = CFNClient(region_stack_name, **kwargs)
            CFNClient.clients[region_stack_name] = cfn_client

        return cfn_client

    def __init__(self, region_stack_name, **kwargs):
        """
        :param region: AWS region
        :type region: str
        """
        self.logger = logging.getLogger(__name__)
        self.region = region_stack_name
        self.aws_client = AWSClient('cloudformation', region_stack_name=region_stack_name, **kwargs);
        # map of StackInfo
        self.info = dict()

    def get_active_stacks(self):
        # conserve bandwidth (and API calls) by not listing any stacks in DELETE_COMPLETE state
        #active_stacks = boto_all(self.client._client.list_stacks, StackStatusFilter=[state for state in CFNClient.VALID_STACK_STATUSES
        #                                                                  if state != 'DELETE_COMPLETE'])
        active_stacks = self.aws_client.call("list_stacks", query='StackSummaries', StackStatusFilter=[state for state in CFNClient.VALID_STACK_STATUSES if state != 'DELETE_COMPLETE'])
        return active_stacks

    def stack_exists(self, stack_name):
        """
        Check if a CFN stack exists
        :param stack_name: stack_name of the stack
        :type stack_name: str
        :return: True/False
        :rtype: bool
        """
        active_stacks = self.get_active_stacks()
        return stack_name in [stack['StackName'] for stack in active_stacks if stack['StackStatus']]

    def get_info(self, stack_name, refresh=False):
        """
        Describe CFN stack and return StackInfo
        :param stack_name: stack_name of the stack
        :type stack_name: str
        :return: stack info object
        :rtype: StackInfo
        """
        info = self.info.get(stack_name, None)
        if refresh or info is None:
            if self.stack_exists(stack_name):
                info = StackInfo(self.aws_client, stack_name)
                self.info[stack_name] = info
            elif self.info.get(stack_name, None):
                del self.info[stack_name]
        return info

    def describe_stack_events(self, stack_name):
        """
        Describe CFN stack events
        :param stack_name: stack stack_name
        :type stack_name: str
        :return: stack events
        :rtype: list of boto.cloudformation.stack.StackEvent
        """

        return self.aws_client.call('describe_stack_events', query='StackEvents', StackName=stack_name)
        #return boto_all(self.conn.describe_stack_events, StackName=stack_name)

    def validate(self, template_body):
        return self.aws_client.call('validate_template', TemplateBody=template_body)

    def create_change_set(self, stack_name, template, parameters):
        params = self._convert_params(parameters)
        return self.aws_client.call('create_change_set', StackName=stack_name, TemplateBody=template, Parameters=params, Capabilities=['CAPABILITY_IAM'])

    def delete_change_set(self, stack_name, change_set_name):
        return self.aws_client.call('delete_change_set', StackName=stack_name, ChangeSetName=change_set_name)

    def execute_change_set(self, stack_name, change_set_name):
        return self.aws_client.call('execute_change_set', StackName=stack_name, ChangeSetName=change_set_name, ClientRequestToken="1")

    def list_change_sets(self, stack_name):
        return self.aws_client.call('list_change_sets', StackName=stack_name, query='Summaries')

    def update_stack(self, stack_name, template, parameters):
        """
        Update CFN stack
        :param stack_name: stack stack_name
        :type stack_name: str
        :param template: JSON encodeable object
        :type template: str
        :param parameters: dictionary containing key value pairs as CFN parameters
        :type parameters: dict
        :rtype: bool
        :return: False if there aren't any updates to be performed, True if no exception has been thrown.
        """

        try:
            params = self._convert_params(parameters)
            #self.conn.update_stack(StackName=stack_name, TemplateBody=template, Parameters=params, Capabilities=['CAPABILITY_IAM'])
            return self.aws_client.call('update_stack', StackName=stack_name, TemplateBody=template, Parameters=params, Capabilities=['CAPABILITY_IAM'])
        except botocore.exceptions.ClientError as ex:
            if CFNClient._error_mesg(ex) == 'No updates are to be performed.':
                # this is not really an error, but there aren't any updates.
                return False
            else:
                raise CloudformationException('Error while updating stack %s: %s' % (stack_name, ex.message))
        else:
            return True

    def create_stack(self, stack_name, template, parameters):
        """
        Create CFN stack
        :param stack_name: stack stack_name
        :type stack_name: str
        :param template: JSON encodeable object
        :type template: str
        :param parameters: dictionary containing key value pairs as CFN parameters
        :type parameters: dict
        """

        try:
            params = self._convert_params(parameters)

            #self.conn.create_stack(StackName=stack_name, TemplateBody=template, DisableRollback=True,Parameters=params, Capabilities=['CAPABILITY_IAM'])
            return self.aws_client.call('create_stack', StackName=stack_name, TemplateBody=template, DisableRollback=True, Parameters=params, Capabilities=['CAPABILITY_IAM'])
        except botocore.exceptions.ClientError as ex:
            raise CloudformationException('Error while creating stack %s: %s' % (stack_name, ex.message))

    def delete_stack(self, stack_name):
        """
        Delete CFN stack
        :param stack_name: stack stack_name
        :type stack_name: str
        :param template: JSON encodeable object
        :type template: str
        :param parameters: dictionary containing key value pairs as CFN parameters
        :type parameters: dict
        """

        try:
            #self.conn.delete_stack(StackName=stack_name)
            return self.aws_client.call('delete_stack', StackName=stack_name)
        except botocore.exceptions.ClientError as ex:
            raise CloudformationException('Error while deleting stack %s: %s' % (stack_name, ex.message))

    def tail_stack_events(self, stack_name, initial_entry=None):
        """
        This function is a wrapper around _tail_stack_events(), because a generator function doesn't run any code
        before the first iterator item is accessed (aka .next() is called).
        This function can be called without an `inital_entry` and tail the stack events from the bottom.
        Each iteration returns either:
        1. StackFailStatus object which indicates the stack creation/update failed (last iteration)
        2. StackSuccessStatus object which indicates the stack creation/update succeeded (last iteration)
        3. dictionary describing the stack event, containing the following keys: resource_type, logical_resource_id,
           physical_resource_id, resource_status, resource_status_reason
        A common usage pattern would be to call tail_stack_events('stack') prior to running update_stack() on it,
        thus creating the iterator prior to the actual beginning of the update. Then, after initiating the update
        process, for loop through the iterator receiving the generated events and status updates.
        :param stack_name: stack stack_name
        :type stack_name: str
        :param initial_entry: where to start tailing from. None means to start from the last item (exclusive)
        :type initial_entry: None or int
        :return: generator object yielding stack events
        :rtype: generator
        """
        try:
            if initial_entry is None:
                return self._tail_stack_events(stack_name, len(self.describe_stack_events(stack_name)))
            elif initial_entry < 0:
                return self._tail_stack_events(stack_name, len(self.describe_stack_events(stack_name)) + initial_entry)
            else:
                return self._tail_stack_events(stack_name, initial_entry)
        except botocore.exceptions.ClientError as ex:
            self.logger.error('Failed to describe stack %s, Reason: %s ' % (stack_name, ex))

    def _tail_stack_events(self, stack_name, initial_entry):
        """
        See tail_stack_events()
        """

        previous_stack_events = initial_entry

        while True:
            try:
                stack_info = self.get_info(stack_name, refresh=True)

                if stack_info.statusInProgress():
                    stack_events = self.describe_stack_events(stack_name)

                    if len(stack_events) > previous_stack_events:
                        # iterate on all new events, at reversed order (the list is sorted from newest to oldest)
                        for event in stack_events[:-previous_stack_events or None][::-1]:
                            yield {'resource_type': event.get('ResourceType',''),
                                   'logical_resource_id': event.get('LogicalResourceId',''),
                                   'physical_resource_id': event.get('PhysicalResourceId',''),
                                   'resource_status': event.get('ResourceStatus',''),
                                   'resource_status_reason': event.get('ResourceStatusReason', ''),
                                   'timestamp': event['Timestamp']}

                        previous_stack_events = len(stack_events)

                if stack_info.status().endswith('_FAILED') or \
                        stack_info.status() in ('ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'):
                    yield StackFailStatus(stack_info.status())
                    break
                elif stack_info.status().endswith('_COMPLETE'):
                    yield StackSuccessStatus(stack_info.status())
                    break
            except botocore.exceptions.ClientError as ex:
                #if CFNConnection._error_code(ex) == 400 and str(CFNConnection._error_mesg(ex)) == "Stack [%s] does not exist" % stack_name:
                yield StackUnknownStatus('STACK_GONE')
                break;
            # avoid rate limited
            time.sleep(2)

    def wait_for_status(self, stack_name):
        while True:
            try:
                stack_info = self.get_info(stack_name, refresh=True)
                if stack_info.statusInProgress():
                    self.logger.debug('waiting: operation inprogress stack: %s ' % stack_name)
                else:
                    if stack_info.status().endswith('_COMPLETE'):
                        return StackSuccessStatus(stack_info.status())
                    else:
                        return StackFailStatus(stack_info.status())
            except botocore.exceptions.ClientError as ex:
                return StackUnknownStatus('STACK_GONE')
                break;

            time.sleep(2)


    def _convert_params(self, parameters):
        params = []
        for key, val in parameters.items():
            param = {'ParameterKey': key}
            if val:
                if type(val) is list:
                    param['ParameterValue'] = ",".join(val)
                else:
                    param['ParameterValue'] = val
            else:
                param['ParameterValue'] = True
            params.append(param)
        return params

    @staticmethod
    def _error_code(err):
        return err.response['ResponseMetadata']['HTTPStatusCode']

    @staticmethod
    def _error_mesg(err):
        return err.response['Error']['Message']

def main():
    import os
    import json
    from common.objecthelper import json_encoder

    region = 'us-west-2'
    profile = 'my-aws-west-2'

    this = CFNClient.get_client(region, False, profile=profile)

    #this.conn.describe_stacks(stack_stack_name)[0]
    #print(this.stack_exists(stack_stack_name))
    #info = this.get_info(stack_stack_name)
    #print('describe %s' % info.desc.stack_id)
    #info.template()
    #events = this.tail_stack_events(stack_stack_name, 0)
    #for event in events:
    #    print('event ' + str(event))

    active = this.get_active_stacks()
    print (json.dumps(active, default=json_encoder) )
    info = this.get_info('CloudWatchAlarmsForCloudTrail')
    print (json.dumps(info.template()))
    print (json.dumps(info.resources(), default=json_encoder))

if __name__ == '__main__':
    main()