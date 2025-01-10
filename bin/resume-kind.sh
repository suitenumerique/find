#!/bin/sh
set -o errexit

echo "Resuming docker containers running k8s cluster managed with kind"

docker unpause $(docker ps --filter name=kind-* --filter status=paused --format "{{.Names}}")
