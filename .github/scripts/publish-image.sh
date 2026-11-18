#!/usr/bin/env bash
# Uploads one release image to the S3-compatible bucket. GitHub caps release
# assets at 2 GiB and the images are bigger, so the release only links here.
set -euo pipefail

file=$1
# Downloads of several releases sit side by side in a folder, so each name
# says which release it came from.
base=$(basename "$file")
name="${base%%.*}-$GITHUB_REF_NAME.${base#*.}"
key="releases/$GITHUB_REF_NAME/$name"

# An empty AWS_ENDPOINT_URL is not the same as none, and AWS S3 needs none.
if [ -n "${RELEASE_S3_ENDPOINT:-}" ]; then
  export AWS_ENDPOINT_URL=$RELEASE_S3_ENDPOINT
fi

sha256=$(sha256sum "$file" | cut -d' ' -f1)
aws s3 cp --no-progress --content-type application/octet-stream \
  "$file" "s3://$RELEASE_S3_BUCKET/$key"

{
  echo "name=$name"
  echo "sha256=$sha256"
  echo "url=${RELEASE_DOWNLOAD_URL%/}/$key"
} >>"$GITHUB_OUTPUT"
