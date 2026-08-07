#!/bin/bash
set -xe

name=${1:?release tag is required}

gh release view "$name" >/dev/null 2>&1 ||
  gh release create "$name" --draft --title "$name" --notes ""
