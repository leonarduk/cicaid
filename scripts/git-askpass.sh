#!/bin/sh
# Git receives the non-secret username from the repository URL. Supply the
# release token only when Git asks for the HTTPS password so that the token is
# never persisted in git configuration or exposed in command arguments.
case "${1:-}" in
  [Pp]assword\ for*)
    if [ -z "${GH_TOKEN:-}" ]; then
      echo "git-askpass: GH_TOKEN is required for HTTPS authentication" >&2
      exit 1
    fi
    printf '%s\n' "$GH_TOKEN"
    ;;
  [Uu]sername\ for*) printf '%s\n' "x-access-token" ;;
  *)
    echo "git-askpass: unsupported prompt" >&2
    exit 1
    ;;
esac
