#!/bin/sh
set -o errexit

echo "Pausing docker containers running k8s cluster managed with kind"

docker pause $(docker ps --filter name=kind-* --filter status=running --format "{{.Names}}")
