#!/bin/sh

syft . > sbom/sbom.table.txt
syft . -o spdx > sbom/sbom.spdx
syft . -o spdx-json > sbom/sbom.spdx.json

sudo docker build --tag uno-bot .
sudo $(which syft) uno-bot -o github-json > sbom/sbom-docker.json
