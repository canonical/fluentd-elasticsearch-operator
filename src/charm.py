#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    CONFIG_DIRECTORY = "/etc/fluent/config.d"

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.fluentd_elasticsearch_pebble_ready, self._configure)
        self.framework.observe(self.on.config_changed, self._configure)
        self._container_name = self._service_name = "fluentd-elasticsearch"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(charm=self, ports=[("fluentd", 24224)])

    def _on_install(self, event):
        self._write_config_files()

    def _write_config_files(self):
        base_source_directory = "src/config_files"

        self._write_to_file(
            source_directory=f"{base_source_directory}/forward-input.conf",
            destination_directory=f"{self.CONFIG_DIRECTORY}/forward-input.conf",
        )
        self._write_to_file(
            source_directory=f"{base_source_directory}/general.conf",
            destination_directory=f"{self.CONFIG_DIRECTORY}/general.conf",
        )
        self._write_to_file(
            source_directory=f"{base_source_directory}/output.conf",
            destination_directory=f"{self.CONFIG_DIRECTORY}/output.conf",
        )
        self._write_to_file(
            source_directory=f"{base_source_directory}/system.conf",
            destination_directory=f"{self.CONFIG_DIRECTORY}/system.conf",
        )

    def _write_to_file(self, source_directory: str, destination_directory: str):
        file = open(source_directory, "r")
        file_content = file.read()
        self._container.push(destination_directory, file_content)

    def _configure(self, event):
        if not self._elasticsearch_config_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if self._container.can_connect():
            self.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer()
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        elasticsearch_url, elasticsearch_port = self._get_elasticsearch_config()
        return Layer(
            {
                "summary": "fluentd_elasticsearch layer",
                "description": "pebble config layer for fluentd_elasticsearch",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": "fluentd_elasticsearch",
                        "startup": "enabled",
                        "command": "./run.sh",
                        "environment": {
                            "OUTPUT_HOST": elasticsearch_url,
                            "OUTPUT_PORT": int(elasticsearch_port),
                            "OUTPUT_BUFFER_CHUNK_LIMIT": "2M",
                            "OUTPUT_BUFFER_QUEUE_LIMIT": 8,
                        },
                    }
                },
            }
        )

    def _get_elasticsearch_config(self) -> tuple:
        # TODO: Elasticsearch url and port should be passed through relationship
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")
        return elasticsearch_url_split[0], elasticsearch_url_split[1]

    @property
    def _elasticsearch_config_is_valid(self) -> bool:
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")
        if len(elasticsearch_url_split) != 2:
            return False
        return True


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
