#!/usr/bin/env bash

set -Eeuo pipefail

readonly API_ORIGIN="https://shop.exonplus.ir"
readonly FRONTEND_IMAGE_PREFIX="ghcr.io/pursite/luxury-perfume-frontend@sha256:"

die() {
  echo "frontend release: $*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage:
  frontend-release.sh stamp <dist-directory> <commit-sha>
  frontend-release.sh validate <release-directory> <commit-sha> [image-digest]
  frontend-release.sh prepare <project-directory> <commit-sha> <image-digest>
  frontend-release.sh activate <project-directory> <commit-sha> <image-digest>
EOF
  exit 2
}

require_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "commit SHA must be 40 lowercase hexadecimal characters"
}

require_digest() {
  [[ "$1" =~ ^${FRONTEND_IMAGE_PREFIX}[0-9a-f]{64}$ ]] || \
    die "frontend image must be a lowercase SHA256 GHCR digest"
}

validate_contents() {
  local release_directory=$1

  test -d "$release_directory" || die "release directory does not exist: $release_directory"
  test -f "$release_directory/index.html" || die "index.html is missing"
  test -d "$release_directory/assets" || die "assets directory is missing"
  test -n "$(find "$release_directory/assets" -type f -print -quit)" || \
    die "assets directory is empty"

  while IFS= read -r -d '' entry; do
    [[ -f "$entry" || -d "$entry" ]] || die "release contains a special file: $entry"
    [[ ! -L "$entry" ]] || die "release contains a symlink: $entry"
  done < <(find "$release_directory" -mindepth 1 -print0)

  while IFS= read -r entry; do
    case "$entry" in
      index.html|assets|.release-manifest.json|.frontend-image-digest) ;;
      *) die "unexpected top-level release entry: $entry" ;;
    esac
  done < <(find "$release_directory" -mindepth 1 -maxdepth 1 -printf '%f\n')

  grep -R -F --binary-files=without-match "$API_ORIGIN" \
    "$release_directory/assets" >/dev/null || \
    die "compiled assets do not contain the production API origin"

}

validate_release() {
  local release_directory=$1
  local commit_sha=$2
  local expected_digest=${3:-}
  local manifest

  require_sha "$commit_sha"
  validate_contents "$release_directory"

  test -f "$release_directory/.release-manifest.json" || \
    die "release manifest is missing"
  manifest=$(<"$release_directory/.release-manifest.json")
  [[ "$manifest" == "{\"schema\":1,\"commit_sha\":\"$commit_sha\",\"api_base_url\":\"$API_ORIGIN\"}" ]] || \
    die "release manifest does not match the selected commit and API origin"

  if test -n "$expected_digest"; then
    require_digest "$expected_digest"
    test -f "$release_directory/.frontend-image-digest" || \
      die "frontend image digest marker is missing"
    test "$(<"$release_directory/.frontend-image-digest")" = "$expected_digest" || \
      die "frontend image digest marker does not match the selected artifact"
  elif test -f "$release_directory/.frontend-image-digest"; then
    require_digest "$(<"$release_directory/.frontend-image-digest")"
  fi
}

stamp() {
  [[ $# -eq 2 ]] || usage
  local dist_directory=$1
  local commit_sha=$2

  require_sha "$commit_sha"
  validate_contents "$dist_directory"
  printf '%s\n' \
    "{\"schema\":1,\"commit_sha\":\"$commit_sha\",\"api_base_url\":\"$API_ORIGIN\"}" \
    > "$dist_directory/.release-manifest.json"
  validate_release "$dist_directory" "$commit_sha"
}

prepare() {
  [[ $# -eq 3 ]] || usage
  local project_directory=$1
  local commit_sha=$2
  local image_digest=$3
  local release_root="$project_directory/frontend-releases"
  local release_directory="$release_root/$commit_sha"
  local staging_directory=""
  local container_id=""

  require_sha "$commit_sha"
  require_digest "$image_digest"
  test -d "$project_directory" || die "project directory does not exist"
  mkdir -p "$release_root"

  if [[ -e "$release_directory" || -L "$release_directory" ]]; then
    validate_release "$release_directory" "$commit_sha" "$image_digest"
    return 0
  fi

  staging_directory=$(mktemp -d "$release_root/.${commit_sha}.staging.XXXXXX")
  cleanup() {
    if test -n "$container_id"; then
      docker rm -f "$container_id" >/dev/null 2>&1 || true
    fi
    if test -n "$staging_directory" && test -d "$staging_directory"; then
      chmod -R u+w "$staging_directory" >/dev/null 2>&1 || true
      rm -rf -- "$staging_directory"
    fi
  }
  trap cleanup EXIT

  revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_digest")
  [[ "$revision" == "$commit_sha" ]] || die "frontend image revision label does not match the selected commit"

  container_id=$(docker create "$image_digest" /frontend/index.html)
  test "$(docker inspect --format '{{.State.Status}}' "$container_id")" = created || \
    die "frontend extraction container was not created in the stopped state"
  docker cp "$container_id:/frontend/." "$staging_directory/"
  docker rm "$container_id" >/dev/null
  container_id=""

  validate_release "$staging_directory" "$commit_sha"
  printf '%s\n' "$image_digest" > "$staging_directory/.frontend-image-digest"
  validate_release "$staging_directory" "$commit_sha" "$image_digest"
  find "$staging_directory" -type d -exec chmod 0555 {} +
  find "$staging_directory" -type f -exec chmod 0444 {} +

  if [[ -e "$release_directory" || -L "$release_directory" ]]; then
    die "release directory appeared concurrently; refusing to overwrite it"
  fi
  mv -T -- "$staging_directory" "$release_directory"
  staging_directory=""
  trap - EXIT
}

activate() {
  [[ $# -eq 3 ]] || usage
  local project_directory=$1
  local commit_sha=$2
  local image_digest=$3
  local release_directory="$project_directory/frontend-releases/$commit_sha"
  local temporary_link="$project_directory/.frontend-current.${commit_sha}.$$"

  require_sha "$commit_sha"
  require_digest "$image_digest"
  validate_release "$release_directory" "$commit_sha" "$image_digest"

  cleanup_link() {
    if test -L "$temporary_link"; then
      rm -f -- "$temporary_link"
    fi
  }
  trap cleanup_link EXIT
  ln -s "frontend-releases/$commit_sha" "$temporary_link"
  mv -T -- "$temporary_link" "$project_directory/frontend-current"
  temporary_link=""
  trap - EXIT
}

main() {
  [[ $# -ge 1 ]] || usage
  case "$1" in
    stamp) shift; stamp "$@" ;;
    validate) shift; [[ $# -ge 2 && $# -le 3 ]] || usage; validate_release "$@" ;;
    prepare) shift; prepare "$@" ;;
    activate) shift; activate "$@" ;;
    *) usage ;;
  esac
}

main "$@"
