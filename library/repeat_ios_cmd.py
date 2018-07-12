#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=C0111,E0611

# (c) 2018, Takamitsu IIDA (@takamitsu-iida)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'metadata_version': '1.1', 'status': ['preview'], 'supported_by': 'community'}

DOCUMENTATION = """
---
module: repeat_ios_cmd
version_added: "2.5"
author: "Takamitsu IIDA (@takamitsu-iida)"
short_description: Run commands repeatedly on remote devices running Cisco IOS
description:
  - Sends arbitrary commands to an ios node and repeat it specified number.
    This module returns start and end time.
  - This module does not support configuration commands.
notes:
  - Tested against Cisco IOS XE Software, Version 16.03.05
options:
  commands:
    description:
      - List of commands to send to the remote ios device.
    required: true
  repeat:
    description:
      - Numbere to be repeated.
    default: 1
  sleep:
    description:
      - Second between command.
    default: 1
  logdir:
    description:
      - Log directory name
    default: log
  logfile:
    description:
      - Output file name
    default: repeat_ios_cmd.log
"""

EXAMPLES = r"""
- name: execute command on cisco devices
  hosts: 11f_routers
  gather_facts: False
  serial: 100

  vars:
    #  - include: vars/exec_commands.yml
    exec_commands:
      - "show process cpu | in CPU"
      # - "ping 127.0.0.1"

  tasks:
    - name: run exec commands on remote nodes
      repeat_ios_cmd:
        commands: "{{ exec_commands }}"
        sleep: 1
        repeat: 10
        store_stdout: false
        logdir: ./log
        logfile: "{{ inventory_hostname | default('cmd')}}.log"
      register: r
"""

RETURN = """
stdout:
  description: The datetime of start and end of command execution
  returned: always
  type: list
  sample: ['start date', 'end date']

stdout_lines:
  description: The value of stdout split into a list
  returned: always
  type: list
  sample: [['start date'], ['end date']]
"""


from datetime import datetime
import os
import time

from ansible.module_utils.network.ios.ios import get_connection, ios_argument_spec
from ansible.module_utils._text import to_text, to_bytes
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.network.common.utils import ComplexList
from ansible.module_utils.six import string_types


def to_lines(stdout):
  for item in stdout:
    if isinstance(item, string_types):
      item = str(item).split('\n')
    yield item


def parse_commands(module, warnings):
  command = ComplexList(dict(command=dict(key=True), prompt=dict(), answer=dict()), module)
  commands = command(module.params['commands'])
  for item in list(commands):
    if item['command'].startswith('conf'):
      module.fail_json(msg='does not support config commands')
    if module.check_mode:
      if not item['command'].startswith('show'):
        warnings.append('only show commands are supported when using check mode, not executing `%s`' % item['command'])
        commands.remove(item)

  return list(commands)


def repeat_commands(module, commands, check_rc=True):
  responses = list()
  responses.append("START: " + datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

  logdir = module.params['logdir']
  logfile = module.params['logfile']
  log_path = to_bytes(os.path.join(logdir, logfile))
  repeat = module.params['repeat']
  sleep = module.params['sleep']
  store_stdout = module.params['store_stdout']

  connection = get_connection(module)

  if not module.check_mode:
    while repeat > 0:
      repeat -= 1
      for cmd in commands:
        if isinstance(cmd, dict):
          command = cmd['command']
          prompt = cmd['prompt']
          answer = cmd['answer']
        else:
          command = cmd
          prompt = None
          answer = None

        try:
          out = connection.get(command, prompt, answer)
        except ConnectionError as e:
          if check_rc:
            raise
          else:
            module.fail_json(msg=u'Failed to get command output %s : %s' % (command, to_text(e)))

        try:
          out = to_text(out, errors='surrogate_or_strict')
        except UnicodeError:
          module.fail_json(msg=u'Failed to decode output : %s' % (command))

        # to reduce memory consumption, store_stdout is set to False by default
        if store_stdout:
          responses.append(out)

        try:
          with open(log_path, "a") as f:
            f.write(command + "\n")
            f.write(out + "\n")
            f.write("\n")
        except EnvironmentError as e:
          module.fail_json(msg=u'Failed to write output %s : %s' % (command, to_text(e)))

        if sleep > 0 and repeat > 0:
          time.sleep(sleep)

  responses.append("END: " + datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
  return responses


def main():
  """main entry point for module execution
  """
  argument_spec = dict(
    commands=dict(type='list', required=True),
    repeat=dict(default=1, type='int'),
    sleep=dict(default=0, type='int'),
    store_stdout=dict(default=False, type='bool'),
    logdir=dict(default="log", type='str'),
    logfile=dict(default='repeat_ios_cmd.log', type='str'))

  argument_spec.update(ios_argument_spec)

  module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

  result = {'changed': False}

  logdir = module.params['logdir']
  if not os.path.isdir(logdir):
    try:
      os.makedirs(logdir)
    except OSError as e:
      module.fail_json(msg=u'Failed to create log directory: %s' % (to_text(e)))

  warnings = list()
  commands = parse_commands(module, warnings)
  result['warnings'] = warnings

  responses = repeat_commands(module, commands)

  result.update({'changed': False, 'stdout': responses, 'stdout_lines': list(to_lines(responses))})

  module.exit_json(**result)


if __name__ == '__main__':
  main()
