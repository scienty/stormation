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
CFNStack represents one independent cloud formation stack
"""
import logging
import json, yaml
import jmespath
from cfn.cfn_client import CFNClient, StackSuccessStatus, StackFailStatus, StackUnknownStatus
from pathlib import Path
import jinja2
from common.langhelper import importFromURI as importPythonFile
from common.s3bucket import  put_template as put_template_to_s3

logger = logging.getLogger(__name__)

class CFNStack(object):
    def __init__(self, key, name, aws_region, enabled:bool=False, **kwargs):
        self.key = key
        self.name = name
        self.aws_region = aws_region
        self.aws_account = kwargs.get('aws_account', None)
        self.depends_on = {}
        self.kwargs = kwargs
        self.cfn_vars = {}
        self.enabled = enabled
        if len(key) <= 0 or len(name) <=0 or len(aws_region) <= 0:
            logger.critical("Stack key, name and aws_region are required fields.")
            exit(1)

        self.cfn_client = CFNClient.get_client(aws_region, **kwargs)

    def add_dependency(self, stack):
        self.depends_on[stack.key] = stack

    def exists(self):
        return self.cfn_client.stack_exists(self.name)

    def get_cf_variables(self, refresh=False):
        """
        Get a variable from a existing cloudformation stack, var_type should be
        parameter, inventory or output.
        If using inventory, provide the logical ID and this will return the
        Physical ID
        """
        if len(self.cfn_vars) > 0 and not refresh:
            return self.cfn_vars

        info = self.cfn_client.get_info(self.name, refresh)
        parameters = dict()
        outputs = dict()
        resources = dict()

        for param in info.parameters():
            parameters[param.get('ParameterKey')] = str(param.get('ParameterValue'))

        for output in info.outputs():
            outputs[output.get('OutputKey')] = str(output.get('OutputValue'))

        for res in info.resources():
            resources[res.get('LogicalResourceId')] = str(res.get('PhysicalResourceId'))

        self.cfn_vars = {
            'Parameters': parameters,
            'Outputs': outputs,
            'Resources': resources
        }

        return self.cfn_vars


class CFNStackData(CFNStack):
    OP_MERGE = 1
    OP_CREATE = 2
    OP_UPDATE = 3
    OP_DELETE = 4
    """
    
    """
    def __init__(self, key, name, aws_region, template, config=dict(), params=dict(), tags=dict(),
                 sns_topic_arn='', **kwargs):
        super(CFNStackData, self).__init__(key, name, aws_region, True, **kwargs)

        self.config = config
        if type(config) is not dict:
            logger.critical("Config for stack %s must be of type dict not %s" % (self.key, type(config)))
            exit(1)

        self.params = params
        if type(self.params) is not dict:
            logger.critical("Parameters for stack %s must be of type dict not %s" % (self.key, type(self.params)))
            exit(1)

        self.tags = tags
        if type(self.tags) is not dict:
            logger.critical("Tags for stack %s must be of type dict not %s" % (self.key, type(self.tags)))
            exit(1)

        self.file = Path(template)
            
        if not self.file.exists() or not self.file.is_file():
            raise Exception('Can not read file %s' % str(self.file))

        self.sns_topic_arn = sns_topic_arn

        #self.validate(**kwargs)

        self.plugin = importPythonFile(str(self.file), True)
        if self.plugin and hasattr(self.plugin, 'init'):
            self.plugin.init(self)


    def _load_template(self):
        import re, mmap

        with open(str(self.file), 'r+') as f:
            mp = f.read()
            docs = re.split(r'[\r\n\s]*---[\r\n]+', mp)
            raw_template = ""
            raw_config = ""

            if len(docs) == 1:
                raw_template = docs[0]
            elif len(docs) == 2:
                raw_template = docs[1]
            elif len(docs) == 3:
                raw_config = docs[1]
                raw_template = docs[2]

            return (raw_config, raw_template)

    def compile(self, uploadToS3=False):
        for stack in self.depends_on.values():
            if not stack.exists():
                raise Exception("Dependent stack %s for %s does not exist" % (stack.name, self.name))

        context = self._get_context()
        self.config = self._resolve_references('config', self.config, context)

        context = self._get_context()
        self.params = self._resolve_references('params', self.params, context)

        context = self._get_context()
        self.tags = self._resolve_references('tags', self.tags, context)

        context = self._get_context()
        raw_config, raw_template = self._load_template()

        loader = jinja2.loaders.FileSystemLoader(str(self.file.parent))
        jinja_env = jinja2.Environment(loader=loader)
        # render config from tempalte
        if len(raw_config.strip()) > 0:
          template = jinja_env.from_string(raw_config)
          template.globals['context'] = context
          config_string = template.render(context)

          local_config = yaml.safe_load(config_string)
          local_config = self._resolve_references('config', local_config, context)
          template_context = local_config | context
        else:
          template_context = context

        if self.plugin and hasattr(self.plugin, 'prepare_context'):
            template_context = self.plugin.prepare_context(template_context)
            if template_context is None:
                logger.warning("You may have forgotten to return context in plugin " + self.key+ ".py")

        template_actual = jinja_env.from_string(raw_template)
        template_actual.globals['context'] = template_context
        self.cfn_template = template_actual.render(template_context)
        print(self.cfn_template)
        #exit(0)

        if(uploadToS3):
            self.s3_url = put_template_to_s3(self.name, self.cfn_template)
            resp = self.cfn_client.validate(template_url=self.s3_url)

    def cf_retain_constructor(self, loader, tag_suffix, node):
        return "!{} {}".format(tag_suffix, node.value)

    def _get_context(self, refresh=False):
        context = {
            'stack_name': self.name,
            'config': self.config,
            'parameters': self.params,
            'tags': self.tags
        }

        for key, stack in self.depends_on.items():
            context[key] = stack.get_cf_variables(refresh)

        return context


    def _resolve_references(self, name, item, context):
        if type(item) is str:
            return self.resolve_reference(item, context) if item.startswith("$") and not item.startswith("$$") else item
        elif type(item) is dict:
            for key, value in item.items():
                item[key] = self._resolve_references(name, value, context)
            return item
        elif type(item) is list:
            new_list = []
            for list_item in item:
                new_list.append(self._resolve_references(name, list_item, context))
            return new_list
        else:
            try:
                new_items = []
                for sub_item in item:
                    new_items.append(self._resolve_references(name, sub_item, context))
                return new_items
            except TypeError:
                return item

    def resolve_reference(self, attr, context):
        '''

        :param attr:    config.variable
                        parameters.variable
                        tags.variable
                        stack_name.outputs.variable
                        stack_name.resources.variable
                        stack_name.parameters.variable

        :return:
        '''
        if attr.startswith("$"):
            attr = attr[1:]

        splits = attr.split('.')
        base = splits[0]
        # case of nested variables
        env = context.get(base, None)
        if env is None:
            raise Exception('Can not find context %s to resolve %s' % (base, attr))

        query = attr[attr.index(".") + 1:]
        query = jmespath.compile(query)
        data = query.search(env)

        if data is not None:
            return data

        # TODO: try without qualified name

        raise Exception('Failed to resolve variable %s ' % attr)

########## cleanup
    def validate(self, **kwargs):
        if self.aws_account is not None:
            if str(self.aws_account) != str(self.cfn_client.aws_client.aws_account):
                self.logger.critical("aws_account does not match with aws credentials provided.")
                exit(1)



        #if not self.read_template():
        #    raise Exception("Failed to read template file %s" % self.template)
        #result = self.cfn_client.validate(self.template_body)
        #self._capabilities = result.get('Capabilities', [])
        # remove template body from memory
        #del self.template_body
            #iam_conn = iam.connect_to_aws_region(self.aws_region)
            #user_response = iam_conn.get_user()['get_user_response']
            #user_result = user_response['get_user_result']
            #aws_account = user_result['user']['arn'].split(':')[4]

    def delete_stack(self, wait=True):
        if not self.exists():
            self.logger.info("Stack does not exist in aws")

        self.cfn_client.delete_stack(stack_name=self.name)

        return self.wait_on_events(None) if wait else None


    def create_update_stack(self, wait=True):

        if self.exists():
            info = self.get_info(True)
            if info.statusInProgress():
                logger.info("Waiting for the existing operation to complete")
                if wait:
                    self.wait_on_events(0)
                    info = self.get_info(True)
                else:
                    raise Exception("Another operation is in progress for stack %s", self.name)

            if info.status() == 'CREATE_FAILED':
                self.delete_stack()

        self.compile(uploadToS3=True)

        if self.exists():
            resp = self.cfn_client.update_stack(stack_name=self.name, template_url=self.s3_url, parameters=self.params)
            if resp:
                logger.info('StackID:%s'%resp['StackId'])
            return self.wait_on_events(None) if wait else None
        else:
            resp = self.cfn_client.create_stack(stack_name=self.name, template_url=self.s3_url, parameters=self.params)
            if resp:
                logger.info('StackID:%s' % resp['StackId'])
            return self.wait_on_events(0) if wait else None


    def apply(self, op=1, strict=True, wait=True):
        """
        Apply a template operation to cloud formation based on the mode
        :param operation: MERGE, CREATE, UPDATE, DELETE
        :return:
        """

        exists = self.cfn_client.stack_exists(self.name)
        if op == CFNStackData.OP_DELETE:
            if exists:
                if self.check_deps_delete():
                    self.cfn_client.delete_stack(self.name)
                    return self.wait_on_events(-1) if wait else None
                else:
                    raise Exception("Cannot delete stack %s with existing dependencies" % self.name)
            else:
                return None

        if exists:
            info = self.cfn_client.get_info(self.name, True)
            if info.statusFailed():
                self.cfn_client.delete_stack(self.name)
                del_status = self.wait_on_events(-1)
                if type(del_status) is StackFailStatus:
                    raise Exception("Failed to delete previously failed stack %s" % self.name)
                exists = False

        if not self.check_deps_create():
            raise Exception("Dependencies for stack %s are not active" % self.name)
        if not self.read_template():
            raise Exception("Failed to read template file %s" % self.template)
        if not self.resolve_params():
            raise Exception("Failed to resolve parameters for stack %s" % self.name)

        """
        if op == CFNStack.OP_DELETE:
            if strict and not exists:
                raise "Cannot delete non existing stack %s" % self.name
        elif op == CFNStack.OP_CREATE:
            if strict and exists:
                raise "Stack already exist %s " % self.name
        elif op == CFNStack.OP_UPDATE:
            if strict and not exists:
                raise "Cannot update non existing stack %s" % self.name
        """

        if exists:
            self.cfn_client.update_stack(name=self.name, template=self.template_body, parameters=self.params)
            return self.wait_on_events(None) if wait else None
        else:
            self.cfn_client.create_stack(name=self.name, template=self.template_body, parameters=self.params)
            return self.wait_on_events(0) if wait else None

    def wait_on_events(self, start_event_log):
        stack_events_iterator = self.cfn_client.tail_stack_events(self.name, start_event_log)

        if stack_events_iterator is None:
            return

        for event in stack_events_iterator:
            if isinstance(event, StackFailStatus):
                logger.error('Stack operation failed: %s', event)
                return event
            elif isinstance(event, StackSuccessStatus):
                logger.info('Stack operation succeeded: %s', event)
                return event
            elif isinstance(event, StackUnknownStatus):
                logger.info('Stack operation unknown: %s', event)
                return event
            else:
                logger.info(
                    '%(resource_type)s %(logical_resource_id)s %(physical_resource_id)s %(resource_status)s %(resource_status_reason)s',
                    event)

    def wait_for_status(self):
        self.cfn_client.wait_for_status(self.name)

    def dep_exist(self):
        """
        Check whether stacks we depend on exist in CloudFormation
        return: (total, exist)
        """
        total = len(self.depends_on)
        exist = 0
        for dep in self.depends_on:
            if dep.exists():
                exist += 1

        return (total, exist)


    def get_info(self, refresh=False):
        """
        get the remote stack info
        """
        return self.cfn_client.get_info(self.name, refresh)

    def get_params_tuples(self):
        """
        Convert param dict to array of tuples needed by boto
        """
        tuple_list = []
        if len(self.params) > 0:
            for param in self.params.keys():
                tuple_list.append((param, self.params[param]))
        return tuple_list

    def create_change_set(self, change_set_name):
        """
        creat and get the change set from AWS
        """
        stack_info = self.cfn_client.describe_stack(self.name)
        if stack_info is None:
            return None

        change_set_name = "cfn_stack_" + self.name
        #blindly delete existing change set
        del_status = self.cfn_client.delete_change_set(self.name, change_set_name)
        cre_status = self.cfn_client.create_change_set(self.name, template=self.template_body, parameters=self.params)


    def template_uptodate(self):
        """
        Check if template in this stack is update date with CFN
        """
        stack_info = self.cfn_client.describe_stack(self.name)
        if stack_info is None:
            return False

        rem_template = json.loads(stack_info.template())
        loc_template = json.loads(self.template_body)
        if rem_template == loc_template:
                return True
        return False

    def params_uptodate(self, current_cf_stacks):
        """
        Check if parameters in this stack are up to date with CFN
        """
        stack_info = self.cfn_client.get_info(self.name)
        if stack_info is None:
            return False

        # If number of params in CF and this stack obj dont match,
        # then it needs updating
        if len(stack_info.parameters()) != len(self.params):
            msg = "New and old parameter lists are different lengths for %s"
            self.logger.debug(msg, self.name)
            return False

        for param in stack_info.parameters():
            # check if param in CF exists in our new parameter set,
            # if not they are differenet and need updating
            key = param.key
            value = param.value
            if key not in self.params:
                msg = ("New params are missing key %s that exists in CF " +
                       "for %s stack already.")
                self.logger.debug(msg, key, self.name)
                return False
            # if the value of parameters are different, needs updating
            if self.params[key] != value:
                msg = "Param %s for stack %s has changed from %s to %s"
                self.logger.debug(msg, key, self.name,
                                  value, self.params[key])
                return False

        # We got to the end without returning False, so must be fine.
        return True
