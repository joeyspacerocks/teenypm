# pm
A tiny CLI project manager

## Install

pm requires Python 3 and colorama to be installed.

pm is a single script which can be run by either giving it execute permissions, or running it via Python)

## Usage

* `pm` | `pm show` - show open issues
* `pm all` | `pm show all` - show all issues
* `pm show [tags]` - show issues with matching tags
* `pm tags` - show a summary of all tags with issue counts
* `pm add <tags> <title> [points]` - add an issue with optional complexity points (defaults to 1)
* `pm rm <id>` - remove an issue
* `pm end <id>` - mark issue as completed
* `pm tag <tag> <id>` - add a tag to an issue
* `pm untag <tag> <id>` - remove a tag from an issue
* `pm tag <tag> <id>` - add a tag to an issue
* `pm burn` - show a burndown chart with estimated finish time
* `pm plan [tag]` - open an editor for entering multiple issues, optionally tagged with `<tag>`
