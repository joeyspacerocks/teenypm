# teenypm
A teeny, tiny CLI project manager.

## Install

`teenypm` requires Python 3.7 and [colorama](https://pypi.org/project/colorama/).

`> pip3 install teenypm`

Once installed you can execute it using:

`pm`

## Usage

When run `pm` will create a small sqlite file in your current working directory named `pm.db`.

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

You can specify an alternative by setting the `EDITOR` environment variable.

For example, to use VS Code:

`export EDITOR="code --wait --new-window"`

(Assumes that the `code` command has been installed from VS Code - see https://code.visualstudio.com/docs/setup/mac#_launching-from-the-command-line.)
