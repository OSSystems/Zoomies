#!/usr/bin/env bash
# Prepares a Cloudflare R2 bucket and the GitHub `release` environment for the
# Release workflow. Run it once, and again to rotate the bucket's key.
#
#   CLOUDFLARE_API_TOKEN=... nix shell --inputs-from . nixpkgs#awscli2 nixpkgs#gh \
#     nixpkgs#jq --command .github/scripts/setup-release-bucket.sh [hostname] [bucket]
#
# The bucket defaults to zoomies-releases, and the hostname, which must be in a
# zone of the same Cloudflare account, to zoomies.ossystems.tech. The token
# needs Account > Workers R2 Storage: Edit, Account > Account API Tokens: Edit,
# Zone > Zone: Read and Zone > DNS: Edit; gh must be logged in as a repository
# admin.
set -euo pipefail

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
repo=${GITHUB_REPOSITORY:-OSSystems/zoomies}
api=https://api.cloudflare.com/client/v4

cf() {
  local method=$1 path=$2
  shift 2
  local reply
  reply=$(curl -sS -X "$method" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    -H "Content-Type: application/json" "$api$path" "$@")
  if [ "$(jq -r .success <<<"$reply")" != true ]; then
    echo "Cloudflare $method $path failed: $(jq -c .errors <<<"$reply")" >&2
    exit 1
  fi
  jq .result <<<"$reply"
}

accounts=$(cf GET /accounts)
if [ "$(jq length <<<"$accounts")" != 1 ]; then
  echo "The token reaches several accounts; give it only one." >&2
  exit 1
fi
account=$(jq -r '.[0].id' <<<"$accounts")

hostname=${1:-zoomies.ossystems.tech}
bucket=${2:-zoomies-releases}
echo "Bucket: $bucket"

# The zone is the longest one the hostname ends in, so a delegated subzone
# wins over its parent.
zone=
candidate=$hostname
while [ -z "$zone" ] && [[ $candidate == *.* ]]; do
  candidate=${candidate#*.}
  zone=$(cf GET "/zones?account.id=$account&name=$candidate" | jq -r '.[0].id // empty')
done
if [ -z "$zone" ]; then
  echo "No zone of this account holds $hostname." >&2
  exit 1
fi
echo "Zone: $candidate"
if ! cf GET "/accounts/$account/r2/buckets/$bucket/domains/custom" |
  jq -e --arg host "$hostname" '.domains[] | select(.domain == $host)' >/dev/null; then
  cf POST "/accounts/$account/r2/buckets/$bucket/domains/custom" --data "$(
    jq -n --arg host "$hostname" --arg zone "$zone" \
      '{domain: $host, zoneId: $zone, enabled: true, minTLS: "1.2"}'
  )" >/dev/null
fi
# The r2.dev address is rate limited and would be a second way in; the
# hostname replaces it.
cf PUT "/accounts/$account/r2/buckets/$bucket/domains/managed" \
  --data '{"enabled": false}' >/dev/null
public_url=https://$hostname
echo "Public URL: $public_url"

# An R2 S3 key is an API token: its id is the key id and the SHA-256 of its
# value the secret. Scoping it to object writes in this one bucket keeps a
# leaked key away from the rest of the account.
group=$(cf GET "/accounts/$account/tokens/permission_groups" |
  jq -r '.[] | select(.name == "Workers R2 Storage Bucket Item Write") | .id')
token=$(cf POST "/accounts/$account/tokens" --data "$(
  jq -n --arg group "$group" \
    --arg resource "com.cloudflare.edge.r2.bucket.${account}_default_$bucket" \
    --arg name "zoomies-release-$(date -u +%Y%m%d%H%M%S)" \
    '{name: $name, policies: [{effect: "allow",
      permission_groups: [{id: $group}], resources: {($resource): "*"}}]}'
)")
key_id=$(jq -r .id <<<"$token")
key_secret=$(jq -r .value <<<"$token" | tr -d '\n' | sha256sum | cut -d' ' -f1)
endpoint=https://$account.r2.cloudflarestorage.com
echo "Created key $key_id"

# Only tags may deploy to the environment, so branch pushes and pull requests
# never see the key.
jq -n '{deployment_branch_policy: {protected_branches: false, custom_branch_policies: true}}' |
  gh api -X PUT "repos/$repo/environments/release" --input - >/dev/null
if ! gh api "repos/$repo/environments/release/deployment-branch-policies" \
  --jq '.branch_policies[] | select(.type == "tag" and .name == "v*")' | grep -q .; then
  gh api "repos/$repo/environments/release/deployment-branch-policies" \
    -f name='v*' -f type=tag >/dev/null
fi
gh secret set RELEASE_S3_ACCESS_KEY_ID --repo "$repo" --env release --body "$key_id"
gh secret set RELEASE_S3_SECRET_ACCESS_KEY --repo "$repo" --env release --body "$key_secret"
gh variable set RELEASE_S3_BUCKET --repo "$repo" --env release --body "$bucket"
gh variable set RELEASE_S3_ENDPOINT --repo "$repo" --env release --body "$endpoint"
gh variable set RELEASE_S3_REGION --repo "$repo" --env release --body auto
gh variable set RELEASE_DOWNLOAD_URL --repo "$repo" --env release --body "$public_url"

# A new key takes a few seconds to work, and a release should not be the
# first to find out the hostname does not serve the bucket.
echo "Checking an upload and a public download..."
probe=releases/.setup-check
export AWS_ACCESS_KEY_ID=$key_id AWS_SECRET_ACCESS_KEY=$key_secret
export AWS_DEFAULT_REGION=auto AWS_ENDPOINT_URL=$endpoint
for attempt in 1 2 3 4 5 6; do
  if echo ok | aws s3 cp --only-show-errors - "s3://$bucket/$probe" 2>/dev/null; then
    break
  fi
  [ "$attempt" = 6 ] && { echo "The new key cannot write to $bucket." >&2; exit 1; }
  sleep 10
done
# A new hostname needs its certificate issued before it serves anything.
for attempt in $(seq 30); do
  if [ "$(curl -fsS "$public_url/$probe" 2>/dev/null)" = ok ]; then
    break
  fi
  if [ "$attempt" = 30 ]; then
    echo "Uploaded, but $public_url/$probe is not readable after 10 minutes." >&2
    exit 1
  fi
  sleep 20
done
aws s3 rm --only-show-errors "s3://$bucket/$probe"
echo "Done: releases will be published to $public_url/releases/<tag>/"
