#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re

from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierRequires
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateAvailableEvent as CertifierCertificateAvailableEvent
)
from charms.magma_orc8r_certifier.v0.cert_fluentd import CertFluentdRequires
from charms.magma_orc8r_certifier.v0.cert_fluentd import (
    CertificateAvailableEvent as FluentdCertificateAvailableEvent
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from typing import Union

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    BASE_CERTS_PATH = "/certs"
    CONFIG_DIRECTORY = "/etc/fluent/config.d"
    REQUIRED_RELATIONS = ["cert-certifier", "cert-fluentd"]

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)
        self._container_name = self._service_name = "fluentd-elasticsearch"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="fluentd", port=24224)],
            service_type="LoadBalancer",
            service_name="fluentd",
        )

        self.cert_certifier = CertCertifierRequires(charm=self, relationship_name="cert-certifier")
        self.cert_fluentd = CertFluentdRequires(charm=self, relationship_name="cert-fluentd")

        self.framework.observe(self.on.fluentd_elasticsearch_pebble_ready, self._configure)
        self.framework.observe(self.on.config_changed, self._configure)

        self.framework.observe(
            self.cert_certifier.on.certificate_available, self._on_certifier_certificate_available
        )
        self.framework.observe(
            self.cert_fluentd.on.certificate_available, self._on_fluentd_certificate_available
        )

    def _configure(self, event: Union[ConfigChangedEvent, PebbleReadyEvent]) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (ConfigChangedEvent or PebbleReadyEvent)
        """
        if not self._elasticsearch_url_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if not self._relations_created:
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certificates to be available.")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._write_config_files()
        self._configure_pebble_layer()
        self.unit.status = ActiveStatus()

    def _on_certifier_certificate_available(
        self, event: CertifierCertificateAvailableEvent
    ) -> None:
        """Saves certifier certificate to certs dir.

        Args:
            event: Juju event (CertifierCertificateAvailableEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        self._container.push(f"{self.BASE_CERTS_PATH}/certifier.pem", event.certificate)

    def _on_fluentd_certificate_available(self, event: FluentdCertificateAvailableEvent) -> None:
        """Saves fluentd certificate and private key to certs dir.

        Args:
            event: Juju event (FluentdCertificateAvailableEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        self._container.push(f"{self.BASE_CERTS_PATH}/fluentd.pem", event.certificate)
        self._container.push(f"{self.BASE_CERTS_PATH}/fluentd.key", event.private_key)

    def _configure_pebble_layer(self) -> None:
        """Configures pebble layer."""
        pebble_layer = self._pebble_layer()
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")

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
        logger.info(f"Writing config file to {destination_directory}")
        with open(source_directory, "r") as file:
            file_content = file.read()
        self._container.push(destination_directory, file_content)

    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble layer
        """
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
                            "OUTPUT_PORT": int(elasticsearch_port),  # type: ignore[dict-item]
                            "OUTPUT_SCHEMA": "https",
                            "OUTPUT_SSL_VERSION": "TLSv1",
                            "OUTPUT_BUFFER_CHUNK_LIMIT": "2M",
                            "OUTPUT_BUFFER_QUEUE_LIMIT": 8,  # type: ignore[dict-item]
                        },
                    }
                },
            }
        )

    def _get_elasticsearch_config(self) -> tuple:
        # TODO: Elasticsearch url and port should be passed through relationship
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")  # type: ignore[union-attr]
        return elasticsearch_url_split[0], elasticsearch_url_split[1]

    @property
    def _elasticsearch_url_is_valid(self) -> bool:
        """Checks whether given Elasticsearch URL is valid or not.

        Returns:
            bool: True/False
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False

    @property
    def _relations_created(self) -> bool:
        """Checks whether required relations are created.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_RELATIONS
            if not self.model.get_relation(relation)
        ]:
            msg = f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    @property
    def _certs_are_stored(self) -> bool:
        """Checks whether the required certs are stored in the container.

        Returns:
            bool: True/False
        """
        if not self._container.can_connect():
            return False
        return all(
            [
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/certifier.pem"),
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/fluentd.key"),
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/fluentd.pem"),
            ]
        )

    def _cert_is_stored(self, cert_path: str) -> bool:
        """Checks whether given cert is stored in the container.

        Args:
            cert_path (str): Certificate path

        Returns:
            bool: True/False
        """
        return self._container.exists(cert_path)


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
