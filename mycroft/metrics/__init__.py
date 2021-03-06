# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import json
import threading
import time

import requests

from mycroft.api import DeviceApi
from mycroft.configuration import Configuration
from mycroft.session import SessionManager
from mycroft.util.log import LOG
from mycroft.util.setup_base import get_version


def report_metric(name, data):
    """
    Report a general metric to the Mycroft servers

    Args:
        name (str): Name of metric. Must use only letters and hyphens
        data (dict): JSON dictionary to report. Must be valid JSON
    """
    if Configuration().get()['opt_in']:
        DeviceApi().report_metric(name, data)


class Stopwatch(object):
    def __init__(self):
        self.timestamp = None

    def start(self):
        self.timestamp = time.time()

    def lap(self):
        cur_time = time.time()
        start_time = self.timestamp
        self.timestamp = cur_time
        return cur_time - start_time

    def stop(self):
        cur_time = time.time()
        start_time = self.timestamp
        self.timestamp = None
        return cur_time - start_time


class MetricsAggregator(object):
    """
    MetricsAggregator is not threadsafe, and multiple clients writing the
    same metric "concurrently" may result in data loss.
    """

    def __init__(self):
        self._counters = {}
        self._timers = {}
        self._levels = {}
        self._attributes = {}
        self.attr("version", get_version())

    def increment(self, name, value=1):
        cur = self._counters.get(name, 0)
        self._counters[name] = cur + value

    def timer(self, name, value):
        cur = self._timers.get(name)
        if not cur:
            self._timers[name] = []
            cur = self._timers[name] = []
        cur.append(value)

    def level(self, name, value):
        self._levels[name] = value

    def clear(self):
        self._counters = {}
        self._timers = {}
        self._levels = {}
        self._attributes = {}
        self.attr("version", get_version())

    def attr(self, name, value):
        self._attributes[name] = value

    def flush(self):
        publisher = MetricsPublisher()
        payload = {
            'counters': self._counters,
            'timers': self._timers,
            'levels': self._levels,
            'attributes': self._attributes
        }
        self.clear()
        count = (len(payload['counters']) + len(payload['timers']) +
                 len(payload['levels']))
        if count > 0:
            LOG.debug(json.dumps(payload))

            def publish():
                publisher.publish(payload)

            threading.Thread(target=publish).start()


class MetricsPublisher(object):
    def __init__(self, url=None, enabled=False):
        conf = Configuration().get()['server']
        self.url = url or conf['url']
        self.enabled = enabled or conf['metrics']

    def publish(self, events):
        if 'session_id' not in events:
            session_id = SessionManager.get().session_id
            events['session_id'] = session_id
        if self.enabled:
            requests.post(
                self.url,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(events), verify=False)
