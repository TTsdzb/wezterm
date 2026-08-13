#!/usr/bin/env bash
set -xe

name=${1:?release tag is required}

if is_draft=$(gh release view "$name" --json isDraft --jq .isDraft 2>/dev/null); then
  if [[ "$is_draft" == "true" ]]; then
    exit 0
  fi

  echo "release $name is already published; refusing to modify it" >&2
  exit 1
fi

gh release create "$name" --draft --title "$name" --notes ""
