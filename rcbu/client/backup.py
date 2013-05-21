import json
import time

import requests

from rcbu.client.command import Command
import rcbu.client.backup_report as backup_report


def _args_from_dict(body):
    args = {
        '_config_id': body['BackupConfigurationId'],
        '_state': body['CurrentState'],
        '_agent_id': body['MachineAgentId'],
        '_machine_name': body['MachineName'],
        '_key': {
            'modulus_hex': body['EncryptionKey']['ModulusHex'],
            'exponent_hex': body['EncryptionKey']['ExponentHex']
        }
    }
    return args


def from_dict(body):
    return Backup(body['BackupId'], _args_from_dict(body))


class Status(object):
    def __init__(self, backup_id, connection):
        self.backup_id = backup_id
        self._connection = connection

    @property
    def id(self):
        return self.backup_id

    @property
    def state(self):
        url = '{0}/{1}/{2}'.format(self._connection.host,
                                   'backup', self.backup_id)
        headers = {'x-auth-token': self._connection.token}
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()['CurrentState']


class Backup(Command):
    def __init__(self, config, connection=None, **kwargs):
        self._config_id = config.id
        self._connection = connection
        [setattr(self, k, v) for k, v in kwargs.items()]

    @property
    def running(self):
        return self._state in ['Queued', 'Preparing', 'InProgress']

    @property
    def state(self):
        return self._state

    @property
    def id(self):
        return getattr(self, '_backup_id', 0)

    def connect(self, connection):
        self._connection = connection

    def _action(self, starting=True):
        action = 'StartManual' if starting else 'StopManual'
        op_id = self._config_id if starting else self.backup_id
        url = '{0}/{1}/{2}'.format(self._connection.host, 'backup',
                                   'action-requested')
        headers = {'X-Auth-Token': self._connection.token,
                   'content-type': 'application/json'}
        data = json.dumps({'Action': action, 'Id': op_id})
        resp = requests.post(url, headers=headers, data=data, verify=False)
        resp.raise_for_status()
        self._state = 'Preparing' if starting else 'Stopped'
        return resp

    def start(self):
        resp = self._action(starting=True)
        self._backup_id = int(resp.content)
        time.sleep(15)
        return Status(self._backup_id, self._connection)

    def stop(self):
        return self._action(starting=False)

    @property
    def report(self):
        url = '{0}/{1}/{2}/{3}'.format(self._connection.host,
                                       'backup', 'report', self.id)
        headers = {'x-auth-token': self._connection.token}
        resp = requests.get(url, headers=headers, verify=False)
        print(url, self._connection)
        resp.raise_for_status()
        print(resp.json())
        return backup_report.from_dict(resp.json())

    def _is_done(self):
        report = self.report
        print(report._state)
        return report._state in ['Completed', 'CompletedWithErrors',
                                 'Failed', 'Stopped', 'Skipped', 'Missed']

    def wait_for_completion(self, poll_interval_seconds=60):
        while not self._is_done():
            time.sleep(poll_interval_seconds)
