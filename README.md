# pm
A tiny CLI project manager.

## Install

`pm` requires Python 3 and [colorama](https://pypi.org/project/colorama/) to be installed.

`pm` is a single script which can be run by either giving it execute permissions and putting it somewhere in your path, or running it using python - e.g.:

`> python3 pm`

## Usage

`pm` will create a small sqlite file in your current working directory when run named `pm.db`.

* `pm` | `pm show` - show open issues
* `pm all` | `pm show all` - show all issues
* `pm show [tags]` - show issues with matching tags
* `pm tags` - show a summary of all tags with issue counts
* `pm add <tags> <title> [points]` - add an issue with optional complexity points (defaults to 1)
* `pm addx <tags> <title> [points]` - same as `pm add` but opens editor for multiline text
* `pm edit <id>` - open an editor to edit issue text
* `pm rm <id>` - remove an issue
* `pm end <id>` - mark issue as completed
* `pm tag <tag> <id>` - add a tag to an issue
* `pm untag <tag> <id>` - remove a tag from an issue
* `pm tag <tag> <id>` - add a tag to an issue
* `pm burn` - show a burndown chart with estimated finish time
* `pm plan [tag]` - open an editor for entering multiple issues, optionally tagged with `<tag>`

## Configuration

The editor used for the `addx`, `edit` and `plan` commands defaults to `vim`.

You can specify an alternative by setting the environment variable `PM_EDITOR`.

For example, to use VS Code:

`export PM_EDITOR="code --wait --new-window"`

(Assumes that the `code` command has been installed from VS Code - see https://code.visualstudio.com/docs/setup/mac#_launching-from-the-command-line.)
