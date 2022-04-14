# Contributing/Hacking

## Developing and testing
Testing is done using `tox` like so:
```shell
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
```

Tox creates virtual environment for every tox environment defined in
[tox.ini](tox.ini). Create and activate a virtualenv with the development requirements:

```bash
source .tox/unit/bin/activate
```

## Building
Building and publishing charms is done using [charmcraft](https://snapcraft.io/install/charmcraft/ubuntu):

```bash
charmcraft pack
```


## Deploying

This charm can be deployed on Kubernetes using `juju deploy`:

```bash
juju deploy ./fluentd-elasticsearch_ubuntu-20.04-amd64.charm --resource fluentd-elasticsearch-image=gcr.io/google-containers/fluentd-elasticsearch:v2.4.0
```

## Publishing

Publishing to charmhub is done through CI/CD leveraging github actions.
