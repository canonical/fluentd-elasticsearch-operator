# fluentd-elasticsearch

## Description

Fluentd is an open-source data collector for a unified logging layer. Fluentd allows you to unify data collection and
consumption for better use and understanding of data. This fluentd charm is specifically built to forward logs to
elasticsearch.

## Usage

```bash
juju deploy fluentd-elasticsearch --trust --channel edge --options elasticsearch-url="yourelasticsearch:9200"
```

## Config

```bash
juju config fluentd-elasticsearch elasticsearch-url="yourelasticsearch:9200"
```

> The elasticseach URL will be modeled using juju relations once there is a kubernetes
> charm for elasticsearch.

## OCI Images

Default: gcr.io/google-containers/fluentd-elasticsearch:v2.4.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
