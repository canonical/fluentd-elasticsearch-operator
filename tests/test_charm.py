# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus

from charm import FluentdElasticsearchCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda charm, ports: None)
    def setUp(self):
        self.harness = testing.Harness(FluentdElasticsearchCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_default_config_when_pebble_ready_then_status_is_blocked(self):
        self.harness.container_pebble_ready(container_name="fluentd-elasticsearch")

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    def test_given_good_config_when_pebble_ready_then_plan_is_filled_with_fluentd_service_content(
        self,
    ):
        hostname = "blablabla"
        port = 80
        config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.container_pebble_ready(container_name="fluentd-elasticsearch")

        self.harness.update_config(key_values=config)

        expected_plan = {
            "services": {
                "fluentd-elasticsearch": {
                    "override": "replace",
                    "summary": "fluentd_elasticsearch",
                    "startup": "enabled",
                    "command": "./run.sh",
                    "environment": {
                        "OUTPUT_HOST": hostname,
                        "OUTPUT_PORT": port,
                        "OUTPUT_BUFFER_CHUNK_LIMIT": "2M",
                        "OUTPUT_BUFFER_QUEUE_LIMIT": 8,
                    },
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("fluentd-elasticsearch").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_good_config_when_pebble_ready_then_status_is_active(self):
        config = {"elasticsearch-url": "abcd:1234"}
        self.harness.container_pebble_ready(container_name="fluentd-elasticsearch")

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == ActiveStatus()

    def test_given_bad_config_when_pebble_ready_then_status_is_blocked(self):
        config = {"elasticsearch-url": "abcd1234"}
        self.harness.container_pebble_ready(container_name="fluentd-elasticsearch")

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )
