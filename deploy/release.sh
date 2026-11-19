#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'
umask 022

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

COMMAND="${1:-}"
if [[ -n "$COMMAND" ]]; then
    shift
fi

PYTHON_BIN="${BWCA_PYTHON:-python3}"
CADDY_BIN="${BWCA_CADDY_BIN:-caddy}"
WEB_ROOT="${BWCA_WEB_ROOT:-/srv/www/bwca}"
RELEASES_DIR="${BWCA_RELEASES_DIR:-/srv/www/bwca-releases}"
CADDYFILE="${BWCA_CADDYFILE:-}"
STAGING_DIR=""

usage() {
    cat <<'EOF'
Usage:
  deploy/release.sh check [options]
  deploy/release.sh deploy [options]
  deploy/release.sh rollback [options]

Commands:
  check       Rebuild and run the complete local release validation.
  deploy      Validate, stage maps/ as a versioned release, atomically switch
              the web-root symlink, validate Caddy, and reload it.
  rollback    Atomically swap the current and previous releases, then reload.

Options:
  --web-root PATH       Caddy web-root symlink (default: /srv/www/bwca)
  --releases-dir PATH   Versioned release directory
                        (default: /srv/www/bwca-releases)
  --caddyfile PATH      Caddyfile to verify, validate, and reload
  --python COMMAND      Python interpreter (default: python3)
  --caddy COMMAND       Caddy executable (default: caddy)
  -h, --help            Show this help

Environment equivalents use the BWCA_ prefix: BWCA_WEB_ROOT,
BWCA_RELEASES_DIR, BWCA_CADDYFILE, BWCA_PYTHON, and BWCA_CADDY_BIN.

The script never invokes sudo, changes DNS, or edits the Caddyfile. The deploy
and rollback commands require an already configured Caddy service and writable
release/web-root paths.
EOF
}

log() {
    printf '[bwca-release] %s\n' "$*"
}

die() {
    printf '[bwca-release] ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]]; then
        case "$STAGING_DIR" in
            "$RELEASES_DIR"/.staging-*) rm -rf -- "$STAGING_DIR" ;;
            *) printf '[bwca-release] Refusing to remove unsafe staging path: %s\n' \
                   "$STAGING_DIR" >&2 ;;
        esac
    fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --web-root)
            [[ $# -ge 2 ]] || die "--web-root requires a path"
            WEB_ROOT="$2"
            shift 2
            ;;
        --releases-dir)
            [[ $# -ge 2 ]] || die "--releases-dir requires a path"
            RELEASES_DIR="$2"
            shift 2
            ;;
        --caddyfile)
            [[ $# -ge 2 ]] || die "--caddyfile requires a path"
            CADDYFILE="$2"
            shift 2
            ;;
        --python)
            [[ $# -ge 2 ]] || die "--python requires a command"
            PYTHON_BIN="$2"
            shift 2
            ;;
        --caddy)
            [[ $# -ge 2 ]] || die "--caddy requires a command"
            CADDY_BIN="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

case "$COMMAND" in
    -h|--help)
        usage
        exit 0
        ;;
    check|deploy|rollback) ;;
    "")
        usage >&2
        exit 2
        ;;
    *)
        usage >&2
        die "unknown command: $COMMAND"
        ;;
esac

if [[ -z "$CADDYFILE" ]]; then
    if [[ "$COMMAND" == "check" ]]; then
        CADDYFILE="$REPO_ROOT/deploy/Caddyfile.example"
    else
        CADDYFILE="/etc/caddy/Caddyfile"
    fi
fi

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

normalize_link_path() {
    local path="$1"
    local parent name
    parent="$(dirname -- "$path")"
    name="$(basename -- "$path")"
    printf '%s/%s\n' "$(realpath -m -- "$parent")" "$name"
}

normalize_deploy_paths() {
    require_command realpath
    # Keep the final component unresolved because it is the symlink managed by
    # this script. Resolving it would turn the web root into its release target.
    WEB_ROOT="$(normalize_link_path "$WEB_ROOT")"
    RELEASES_DIR="$(realpath -m -- "$RELEASES_DIR")"
    CADDYFILE="$(realpath -m -- "$CADDYFILE")"

    [[ "$WEB_ROOT" != "/" ]] || die "web root cannot be /"
    [[ "$RELEASES_DIR" != "/" ]] || die "release directory cannot be /"
    [[ "$WEB_ROOT" != "$RELEASES_DIR" ]] || \
        die "web root and release directory must be different"

    case "$WEB_ROOT/" in
        "$RELEASES_DIR/"*) die "web root cannot be inside the release directory" ;;
    esac
    case "$RELEASES_DIR/" in
        "$WEB_ROOT/"*) die "release directory cannot be inside the web root" ;;
    esac
    for path in "$WEB_ROOT" "$RELEASES_DIR"; do
        case "$path" in
            "$REPO_ROOT"|"$REPO_ROOT"/*)
                die "deployment paths must stay outside the Git checkout: $path"
                ;;
        esac
    done
}

require_clean_checkout() {
    git -C "$REPO_ROOT" diff --quiet --ignore-submodules -- || \
        die "deploy requires a clean checkout (tracked files are modified)"
    git -C "$REPO_ROOT" diff --cached --quiet --ignore-submodules -- || \
        die "deploy requires a clean checkout (changes are staged)"
    local untracked
    untracked="$(git -C "$REPO_ROOT" ls-files --others --exclude-standard)"
    [[ -z "$untracked" ]] || \
        die "deploy requires a clean checkout (untracked files are present)"
}

verify_artifact_shape() {
    [[ -d "$REPO_ROOT/maps" ]] || die "maps/ was not generated"
    for required in index.html lake_search.html bwca_graph_map.html legal.html; do
        [[ -f "$REPO_ROOT/maps/$required" ]] || \
            die "generated artifact is missing maps/$required"
    done

    local unsafe
    unsafe="$(find "$REPO_ROOT/maps" -mindepth 1 \
        \( -type l -o \( ! -type f ! -type d \) \) -print -quit)"
    [[ -z "$unsafe" ]] || die "maps/ contains a symlink or special file: $unsafe"
}

verify_csp() {
    local html_path="$1"
    "$PYTHON_BIN" "$REPO_ROOT/deploy/verify_csp.py" "$html_path" "$CADDYFILE"
}

build_and_validate() {
    require_command "$PYTHON_BIN"
    require_command npm
    require_command git

    cd -- "$REPO_ROOT"
    log "Installing the pinned JavaScript dependencies"
    npm ci
    log "Syncing locally hosted browser libraries"
    npm run vendor
    log "Rebuilding maps/"
    "$PYTHON_BIN" APP.py
    log "Running Python tests"
    "$PYTHON_BIN" -m unittest discover -s tests -v
    log "Validating lake bundles"
    "$PYTHON_BIN" Scripts/validate_lake_bundles.py
    log "Running JavaScript tests"
    npm test
    log "Auditing production JavaScript dependencies"
    npm run audit:prod
    log "Checking for generated-site drift"
    git diff --quiet -- maps || \
        die "rebuild changed tracked files in maps/; commit the deterministic output first"
    [[ -z "$(git ls-files --others --exclude-standard -- maps)" ]] || \
        die "rebuild created untracked files in maps/"
    verify_artifact_shape
    verify_csp "$REPO_ROOT/maps/lake_search.html"
}

validate_caddy() {
    require_command "$CADDY_BIN"
    [[ -r "$CADDYFILE" ]] || die "Caddyfile is not readable: $CADDYFILE"

    if ! awk -v expected="$WEB_ROOT" '
        $1 == "root" && $2 == "*" {
            value = $3
            gsub(/^"|"$/, "", value)
            if (value == expected) found = 1
        }
        END { exit found ? 0 : 1 }
    ' "$CADDYFILE"; then
        die "Caddyfile must contain: root * $WEB_ROOT"
    fi

    log "Validating Caddy configuration"
    "$CADDY_BIN" validate --config "$CADDYFILE" --adapter caddyfile
}

canonical_release_target() {
    local link_path="$1"
    [[ -L "$link_path" ]] || die "expected a symlink: $link_path"
    local target
    target="$(realpath -e -- "$link_path")" || die "broken release symlink: $link_path"
    [[ -d "$target" ]] || die "release target is not a directory: $target"
    case "$target/" in
        "$RELEASES_DIR/"*) printf '%s\n' "$target" ;;
        *) die "release symlink points outside $RELEASES_DIR: $link_path" ;;
    esac
}

atomic_symlink() {
    local target="$1"
    local link_path="$2"
    local temporary="${link_path}.next.$$"
    ln -s -- "$target" "$temporary"
    mv -Tf -- "$temporary" "$link_path"
}

reload_caddy() {
    log "Reloading Caddy"
    "$CADDY_BIN" reload --config "$CADDYFILE" --adapter caddyfile
}

restore_current_link() {
    local old_target="$1"
    if [[ -n "$old_target" ]]; then
        atomic_symlink "$old_target" "$WEB_ROOT"
    elif [[ -L "$WEB_ROOT" ]]; then
        unlink -- "$WEB_ROOT"
    fi
}

deploy_release() {
    normalize_deploy_paths
    require_clean_checkout
    build_and_validate

    mkdir -p -- "$RELEASES_DIR" "$(dirname -- "$WEB_ROOT")"
    require_command flock
    exec 9>"$RELEASES_DIR/.release.lock"
    flock -n 9 || die "another BWCA release or rollback is already running"

    [[ ! -e "$WEB_ROOT" || -L "$WEB_ROOT" ]] || \
        die "web root must be absent or a managed symlink: $WEB_ROOT"

    local old_target=""
    if [[ -L "$WEB_ROOT" ]]; then
        old_target="$(canonical_release_target "$WEB_ROOT")"
    elif [[ -e "$WEB_ROOT.previous" || -L "$WEB_ROOT.previous" ]]; then
        die "previous-release link exists without a current release: $WEB_ROOT.previous"
    fi

    local commit release_id final_dir
    commit="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
    release_id="$(date -u +%Y%m%dT%H%M%SZ)-$commit"
    final_dir="$RELEASES_DIR/$release_id"
    [[ ! -e "$final_dir" ]] || die "release already exists: $final_dir"

    STAGING_DIR="$RELEASES_DIR/.staging-$release_id-$$"
    mkdir -- "$STAGING_DIR"
    log "Staging only the maps/ artifact in $STAGING_DIR"
    cp -a -- "$REPO_ROOT/maps/." "$STAGING_DIR/"
    find "$STAGING_DIR" -type d -exec chmod 0755 {} +
    find "$STAGING_DIR" -type f -exec chmod 0644 {} +
    diff -qr -- "$REPO_ROOT/maps" "$STAGING_DIR" >/dev/null || \
        die "staged release differs from maps/"

    verify_csp "$STAGING_DIR/lake_search.html"
    if [[ -n "$old_target" ]]; then
        verify_csp "$old_target/lake_search.html"
    fi
    validate_caddy

    mv -- "$STAGING_DIR" "$final_dir"
    STAGING_DIR=""
    atomic_symlink "$final_dir" "$WEB_ROOT"

    if ! reload_caddy; then
        log "Caddy reload failed; restoring the prior web root"
        restore_current_link "$old_target"
        die "release was not activated"
    fi

    if [[ -n "$old_target" ]]; then
        if ! atomic_symlink "$old_target" "$WEB_ROOT.previous"; then
            log "Could not preserve the rollback link; restoring the prior release"
            restore_current_link "$old_target"
            reload_caddy || true
            die "release was rolled back because the previous link could not be saved"
        fi
    fi

    log "Release active: $final_dir"
    if [[ -n "$old_target" ]]; then
        log "Rollback target: $old_target"
    else
        log "This was the first managed release; no rollback target exists yet"
    fi
}

rollback_release() {
    normalize_deploy_paths
    require_command "$PYTHON_BIN"
    mkdir -p -- "$RELEASES_DIR"
    require_command flock
    exec 9>"$RELEASES_DIR/.release.lock"
    flock -n 9 || die "another BWCA release or rollback is already running"

    local current_target previous_target
    current_target="$(canonical_release_target "$WEB_ROOT")"
    previous_target="$(canonical_release_target "$WEB_ROOT.previous")"
    [[ "$current_target" != "$previous_target" ]] || \
        die "current and previous links point to the same release"

    verify_csp "$previous_target/lake_search.html"
    validate_caddy
    atomic_symlink "$previous_target" "$WEB_ROOT"

    if ! reload_caddy; then
        log "Caddy reload failed; restoring the release that was current"
        atomic_symlink "$current_target" "$WEB_ROOT"
        die "rollback was not activated"
    fi

    if ! atomic_symlink "$current_target" "$WEB_ROOT.previous"; then
        log "Could not update the previous link; restoring the original release"
        atomic_symlink "$current_target" "$WEB_ROOT"
        reload_caddy || true
        die "rollback was reversed because its safety link could not be saved"
    fi

    log "Rollback active: $previous_target"
    log "The replaced release remains available at: $current_target"
}

case "$COMMAND" in
    check)
        CADDYFILE="$(realpath -m -- "$CADDYFILE")"
        build_and_validate
        log "Release check passed; no server files were changed"
        ;;
    deploy)
        deploy_release
        ;;
    rollback)
        rollback_release
        ;;
esac
