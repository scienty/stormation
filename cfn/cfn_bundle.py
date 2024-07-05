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
"""
Bundle of cloud formation templates
A bundle is an yaml file with configuration parameters and composed of multiple
cloud formation templates with inter dependencies
It supports layered architecture of cloud formation templates infering variables from dependencies
"""
import boto3
import logging
import json
import time
import yaml
import pystache
import os
from pathlib import Path
from cfn.cfn_stack import CFNStack, CFNStackData
from cfn.cfn_client import StackFailStatus, StackSuccessStatus
from common import s3bucket

class CFBundle(object):
    """
    Parse and construct cloud formation stack bundle from yaml file
    """
    def __init__(self, yaml_file, **kwargs):
        self.logger = logging.getLogger(__name__)
        self.logger.propagate = True
        # CFTemplate objects
        self.stacks = []
        self.stack_map = dict()
        self.dependency_map = dict()

        file = Path(yaml_file).resolve()
        self.path = file.parent

        file_handle = open(file, 'r')
        rendered_file = pystache.render(file_handle.read(), dict(os.environ))
        self.input = yaml.safe_load(rendered_file)
        self.config = self.input.get('config', {})
        self.tags = self.config.get('tags', {})

        self.name = self.sanitize_name(self.config.get('bundle_name', 'bundle'))
        self.aws_region = self.config.get('aws_region', None)

        self.aws_profile = kwargs.get('aws_profile', self.config.get('aws_profile', None))
        self.aws_account = self.config.get('aws_account', None)
        kwargs['aws_account'] = self.aws_account

        # create CFStack instances
        input_stacks = self.input['stacks']
        for stack_key in input_stacks.keys():
            stack_def = input_stacks[stack_key];

            stack_name = stack_def.get('name', "%s%s" % (self.name, stack_key))
            stack_name = self.sanitize_name(stack_name)
            stack_region = stack_def.get('aws_region', self.aws_region)

            if stack_def.get('enabled', True):
                template = stack_def['template']
                if not Path(template).is_absolute():
                    stack_template=Path(self.path,  Path(template))

                stack_params = stack_def.get('parameters', dict())
                stack_tags = self.tags | stack_def.get('tags', dict())
                stack_deps = stack_def.get('dependson', [])

                cf_stack = CFNStackData(key=stack_key,
                                   name=stack_name,
                                   aws_region=stack_region,
                                   template=stack_template,
                                   config=self.config,
                                   params=stack_params,
                                   tags = stack_tags,
                                   sns_topic_arn='',
                                   **kwargs)
                self.stack_map[stack_key] = cf_stack
                self.dependency_map[stack_key] = stack_deps
            else:
                cf_stack = CFNStack(key=stack_key,
                                    name=stack_name,
                                    aws_region=stack_region,
                                    **kwargs)

                self.stack_map[stack_key] = cf_stack

        # resolve dependencies
        for stack in self.stack_map.values():
            dep_keys = self.dependency_map.get(stack.key,[])
            for key in dep_keys:
                dep_stack = self.stack_map.get(key, None)
                if dep_stack is None:
                    raise Exception('Dependency stack %s for %s not defined ' % (key,stack.key))
                stack.add_dependency(dep_stack)

        self.stacks = self.sort_stacks()
        s3bucket.init(self.name+ "CFTemplates")

    def sanitize_name(self, name, delimiter=None):
        if delimiter is None:
            name = self.sanitize_name(name, "_")
            name = self.sanitize_name(name, "-")
            name = self.sanitize_name(name, ".")
            return name
        else:
            parts = name.split(delimiter)
            if(len(parts) > 1):
                for i in range(len(parts)):
                    parts[i] = parts[i].title()
                return "".join(parts)
            else:
                return name


    def sort_stacks(self):
        """
        Sort the array of stack_objs so they are in dependancy order
        """
        sorted_stacks = []
        dep_graph = {}
        no_deps = []
        # Add all stacks without dependancies to no_deps
        for stack in self.stack_map.values():
            if len(stack.depends_on) <= 0:
                no_deps.append(stack)
            else:
                dep_graph[stack.key] = []
                for dep_key in stack.depends_on.keys():
                    if self.stack_map.get(dep_key, None):
                        dep_graph[stack.key].append(dep_key)

                if len(dep_graph[stack.key]) == 0:
                    del dep_graph[stack.key]
                    no_deps.append(stack)

        # Perform a topological sort on stacks in dep_graph
        while len(no_deps) > 0:
            stack = no_deps.pop()
            sorted_stacks.append(stack)
            for node in list(dep_graph.keys()):
                for dep_name in dep_graph[node]:
                    if stack.key == dep_name:
                        dep_graph[node].remove(dep_name)
                        if len(dep_graph[node]) < 1:
                            leaf_stack = self.stack_map[node]
                            no_deps.append(leaf_stack)
                            del dep_graph[node]
        if len(dep_graph) > 0:
            self.logger.critical("Stack dependency not found or circular dependency exist")
            self.logger.critical(json.dumps(dep_graph))
            exit(1)
        else:
            return sorted_stacks

    def create_update_bundle(self):
        for stack in self.stacks:
            if stack.enabled:
                stack.create_update_stack()

    def check(self, stack_name=None):
        stack = self.stack_map[stack_name]
        stack.create_update_stack()

    def create(self, stack_name=None):
        """
        Create all stacks in the yaml file.
        Any that already exist are skipped (no attempt to update)
        """
        stack = self.stack_map[stack_name]
        self.logger.info("Starting checks for creation of stack: %s" % stack.name)
        if stack.exists():
            self.logger.info("Stack %s already exists in CloudFormation,"
                                 " skipping" % stack.name)
        else:
            if stack.deps_met(self.cf_desc_stacks) is False:
                self.logger.critical("Dependancies for stack %s not met"
                                         " and they should be, exiting..."
                                         % stack.name)
                exit(1)
            if not stack.populate_params(self.cf_desc_stacks):
                self.logger.critical("Could not determine correct "
                                         "parameters for stack %s"
                                         % stack.name)
                exit(1)

            stack.read_template()
            self.logger.info("Creating: %s, %s" % (
                stack.cf_stack_name, stack.get_params_tuples()))
            try:
                self.cfconn.create_stack(
                    stack_name=stack.cf_stack_name,
                    template_body=stack.template_body,
                    parameters=stack.get_params_tuples(),
                    capabilities=['CAPABILITY_IAM'],
                    notification_arns=stack.sns_topic_arn,
                    tags=stack.tags
                )
            except Exception as exception:
                self.logger.critical(
                    "Creating stack %s failed. Error: %s" % (
                        stack.cf_stack_name, exception))
                exit(1)

            create_result = self.watch_events(
                stack.cf_stack_name, "CREATE_IN_PROGRESS")
            if create_result != "CREATE_COMPLETE":
                self.logger.critical(
                    "Stack didn't create correctly, status is now %s"
                    % create_result)
                exit(1)

            # CF told us stack completed ok.
            # Log message to that effect and refresh the list of stack
            # objects in CF
            self.logger.info("Finished creating stack: %s"
                                % stack.cf_stack_name)
            self.cf_desc_stacks = self._describe_all_stacks()

    def delete(self, stack_name=None, force=False):
        """
        Delete all the stacks from CloudFormation.
        Does this in reverse dependency order.
        Prompts for confirmation before deleting each stack
        """
        # Removing stacks so need to do it in reverse dependency order
        for stack in reversed(self.stacks):
            if stack_name and stack.name != stack_name:
                continue
            self.logger.info("Starting checks for deletion of stack: %s" % stack.name)
            try:
                stack_info = stack.get_info()
                if stack_info is None:
                    self.logger.info("Stack %s doesn't exist in CloudFormation, skipping" % stack.name)
                    continue;
            except:
                self.logger.info("Failed to check stack in %s CloudFormation, still continue" % stack.name)


            confirm = raw_input("Delete stack %s (type 'yes' if so): " % stack.name)
            if not confirm == "yes":
                self.logger.info("Not confirmed delete, skipping...")
                continue
            self.logger.info("Starting delete of stack %s" % stack.name)
            delete_result = stack.apply(op=CFNStack.OP_DELETE, strict=False, wait=True)
            if type(delete_result) == StackFailStatus:
                self.logger.critical("Stack didn't delete correctly, status is now %s" % delete_result)
                exit(1)

            # CF told us stack completed ok. Log message to that effect and
            # refresh the list of stack objects in CF
            self.logger.info("Finished deleting stack: %s" % stack.name)

    def merge(self, stack_name=None):
        for stack in self.stacks:
            if stack_name and stack.name != stack_name:
                continue
            self.logger.info("Starting checks merge stack: %s" % stack.name)

            stack_info = stack.get_info(refresh=True)
            if stack_info and stack_info.statusInProgress():
                self.logger.critical("failed to merge stack %s, another operation in progress %s " % (stack.name, stack_info.status()))
                exit(1)

            status = stack.apply(op=CFNStack.OP_MERGE, strict=False)
            if type(status) is StackFailStatus:
                self.logger.critical("failed to merge stack %s, current status %s " % (stack.name, status))
                exit(1)


    def update(self, stack_name=None):
        """
        Attempts to update each of the stacks if template or parameters are
        different to what's currently in CloudFormation.
        If a stack doesn't already exist. Logs critical error and exits.
        """
        for stack in self.stacks:
            if stack_name and stack.name != stack_name:
                continue
            self.logger.info("Starting checks for update of stack: %s"
                             % stack.name)
            if not stack.exists_in_cf(self.cf_desc_stacks):
                self.logger.critical(
                    "Stack %s doesn't exist in cloudformation, can't update"
                    " something that doesn't exist." % stack.name)
                exit(1)
            if not stack.deps_met(self.cf_desc_stacks):
                self.logger.critical(
                    "Dependencies for stack %s not met and they should be,"
                    " exiting..." % stack.name)
                exit(1)
            if not stack.populate_params(self.cf_desc_stacks):
                self.logger.critical("Could not determine correct parameters"
                                     " for stack %s" % stack.name)
                exit(1)
            stack.read_template()
            template_up_to_date = stack.template_uptodate(self.cf_desc_stacks)
            params_up_to_date = stack.params_uptodate(self.cf_desc_stacks)
            self.logger.debug("Stack is up to date: %s"
                              % (template_up_to_date and params_up_to_date))
            if template_up_to_date and params_up_to_date:
                self.logger.info(
                    "Stack %s is already up to date with CloudFormation,"
                    " skipping..." % stack.name)
            else:
                if not template_up_to_date:
                    self.logger.info(
                        "Template for stack %s has changed." % stack.name)
                    # Would like to get this working. Tried datadiff but can't
                    # stop it from printing whole template
                    # stack.print_template_diff(self.cf_desc_stacks)
                self.logger.info(
                    "Starting update of stack %s with parameters: %s"
                    % (stack.name, stack.get_params_tuples()))
                self.cfconn.validate_template(
                    template_body=stack.template_body)

                try:
                    self.cfconn.update_stack(
                        stack_name=stack.cf_stack_name,
                        template_body=stack.template_body,
                        parameters=stack.get_params_tuples(),
                        capabilities=['CAPABILITY_IAM'],
                        tags=stack.tags,
                    )
                except boto3.exception.BotoServerError as exception:
                    try:
                        e_message_dict = json.loads(exception[2])
                        if (str(e_message_dict["Error"]["Message"]) ==
                           "No updates are to be performed."):
                            self.logger.error(
                                "CloudFormation has no updates to perform on"
                                " %s, this might be because there is a "
                                "parameter with NoEcho set" % stack.name)
                            continue
                        else:
                            self.logger.error(
                                "Got error message: %s"
                                % e_message_dict["Error"]["Message"])
                            raise exception
                    except json.decoder.JSONDecodeError:
                        self.logger.critical(
                            "Unknown error updating stack: %s", exception)
                        exit(1)
                update_result = self.watch_events(
                    stack.cf_stack_name, [
                        "UPDATE_IN_PROGRESS",
                        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS"])
                if update_result != "UPDATE_COMPLETE":
                    self.logger.critical(
                        "Stack didn't update correctly, status is now %s"
                        % update_result)
                    exit(1)

                self.logger.info(
                    "Finished updating stack: %s" % stack.cf_stack_name)

            # avoid getting rate limited
            time.sleep(2)

    def create_change_set(self, stack_name=None):
        """
        Attempts to update each of the stacks if template or parameters are
        different to what's currently in CloudFormation.
        If a stack doesn't already exist. Logs critical error and exits.
        """
        for stack in self.stacks:
            if stack_name and stack.name != stack_name:
                continue
            self.logger.info("Getting change set for stack: %s"
                             % stack.name)
            #if not stack.exists_in_cf(self.cf_desc_stacks):
            #    self.logger.critical(
            #        "Stack %s doesn't exist in cloudformation, can't update"
            #        " something that doesn't exist." % stack.name)
            #    exit(1)
            stack.read_template()
            changes = stack.create_change_set()

            # avoid getting rate limited
            time.sleep(2)
            return changes

    def watch(self, stack_name):
        """
        Watch events for a given CloudFormation stack.
        It will keep watching until its state changes
        """
        if not stack_name:
            self.logger.critical(
                "No stack name passed in, nothing to watch... use -s to "
                "provide stack name.")
            exit(1)
        the_stack = False
        for stack in self.stack_objs:
            if stack_name == stack.name:
                the_stack = stack
        if not the_stack:
            self.logger.error("Cannot find stack %s to watch" % stack_name)
            return False
        the_cf_stack = the_stack.exists_in_cf(self.cf_desc_stacks)
        if not the_cf_stack:
            self.logger.error(
                "Stack %s doesn't exist in CloudFormation, can't watch "
                "something that doesn't exist." % stack_name)
            return False

        self.logger.info(
            "Watching stack %s, while in state %s."
            % (the_stack.cf_stack_name, str(the_cf_stack.stack_status)))
        self.watch_events(
            the_stack.cf_stack_name, str(the_cf_stack.stack_status))

    def watch_events(self, stack_name, while_status):
        """
        Used by the various actions to watch CloudFormation events
        while a stacks in a given state
        """
        try:
            cfstack_obj = self.cfconn.describe_stacks(stack_name)[0]
            events = list(self.cfconn.describe_stack_events(stack_name))
        except boto3.exception.BotoServerError as exception:
            if (str(exception.error_message) ==
               "Stack:%s does not exist" % (stack_name)):
                return "STACK_GONE"

        colors = {
            'blue': '\033[0;34m',
            'red': '\033[0;31m',
            'bred': '\033[1;31m',
            'green': '\033[0;32m',
            'bgreen': '\033[1;32m',
            'yellow': '\033[0;33m',
        }

        status_color_map = {
            'CREATE_IN_PROGRESS': colors['blue'],
            'CREATE_FAILED': colors['bred'],
            'CREATE_COMPLETE': colors['green'],
            'ROLLBACK_IN_PROGRESS': colors['red'],
            'ROLLBACK_FAILED': colors['bred'],
            'ROLLBACK_COMPLETE': colors['yellow'],
            'DELETE_IN_PROGRESS': colors['red'],
            'DELETE_FAILED': colors['bred'],
            'DELETE_COMPLETE': colors['yellow'],
            'UPDATE_IN_PROGRESS': colors['blue'],
            'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS': colors['blue'],
            'UPDATE_COMPLETE': colors['bgreen'],
            'UPDATE_ROLLBACK_IN_PROGRESS': colors['red'],
            'UPDATE_ROLLBACK_FAILED': colors['bred'],
            'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS': colors['red'],
            'UPDATE_ROLLBACK_COMPLETE': colors['yellow'],
            'UPDATE_FAILED': colors['bred'],
        }
        # print the last 5 events, so we get to see the start of the action we
        # are performing
        self.logger.info("Last 5 events for this stack:")
        for event in reversed(events[:5]):
            if self.stackDict[self.name].get('highlight-output', True):
                self.logger.info("%s %s%s\033[0m %s %s %s %s" % (
                    event.timestamp.isoformat(),
                    status_color_map.get(event.resource_status, ''),
                    event.resource_status,
                    event.resource_type,
                    event.logical_resource_id,
                    event.physical_resource_id,
                    event.resource_status_reason,
                ))
            else:
                self.logger.info("%s %s %s %s %s %s" % (
                    event.timestamp.isoformat(),
                    event.resource_status,
                    event.resource_type,
                    event.logical_resource_id,
                    event.physical_resource_id,
                    event.resource_status_reason,
                ))
        status = str(cfstack_obj.stack_status)
        self.logger.info("New events:")
        while status in while_status:
            try:
                new_events = list(
                    self.cfconn.describe_stack_events(stack_name))
            except boto3.exception.BotoServerError as exception:
                if (str(exception.error_message) ==
                   "Stack:%s does not exist" % (stack_name)):
                    return "STACK_GONE"
            count = 0
            events_to_log = []
            while (events[0].timestamp != new_events[count].timestamp or
                   events[0].logical_resource_id !=
                   new_events[count].logical_resource_id):
                events_to_log.insert(0, new_events[count])
                count += 1
            for event in events_to_log:
                if self.stackDict[self.name].get('highlight-output', True):
                    self.logger.info("%s %s%s\033[0m %s %s %s %s" % (
                        event.timestamp.isoformat(),
                        status_color_map.get(event.resource_status, ''),
                        event.resource_status,
                        event.resource_type,
                        event.logical_resource_id,
                        event.physical_resource_id,
                        event.resource_status_reason,
                    ))
                else:
                    self.logger.info("%s %s %s %s %s %s" % (
                        event.timestamp.isoformat(),
                        event.resource_status,
                        event.resource_type,
                        event.logical_resource_id,
                        event.physical_resource_id,
                        event.resource_status_reason,
                    ))
            if count > 0:
                events = new_events[:]
            cfstack_obj.update()
            status = str(cfstack_obj.stack_status)
            time.sleep(5)
        return status

    def _describe_all_stacks(self):
        """
        Get all pages of stacks from describe_stacks API call.
        """
        result = []
        resp = self.cfconn.describe_stacks()
        result.extend(resp)
        while resp.next_token:
            resp = self.cfconn.describe_stacks(next_token=resp.next_token)
            result.extend(resp)
        return result