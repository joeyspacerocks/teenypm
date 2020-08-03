# teenypm
A teeny, tiny CLI project manager.

Suitable for solo development projects; stores data in a local SQLite file, with optional syncing to remote issue systems, such as GitHub.

## Install

`teenypm` requires Python 3 with SQLite installed.

Install using:

`pip3 install teenypm`

Once installed you can execute it using:

`pm`

## Usage

When run `pm` will create a small SQLite file in your current working directory named `pm.db`.

* `pm [-a] [-d]` - show issues, optionally including closed (`-a`), with full dates (`-d`)
* `pm -h` - show help
* `pm <command> -h` show help for command

Optional global flags:

* `-s` - force a sync if a remote system linked (default is to only sync if an hour since last sync)

Subcommands:

* `pm show [-a] [-d] [tags]` - show issues, optionally including closed (`-a`), with full dates (`-d`) and/or filtering by tags
* `pm doing [-d]` - show started issues, optionally with full dates (`-d`)
* `pm tags` - show a summary of all tags with issue counts
* `pm add [-e] <tags> <title> [points]` - add an issue with optional complexity points (defaults to 1), optionally opening an editor (`-e`) for multiline text
* `pm edit <id>` - open an editor to edit issue text
* `pm rm <id>` - remove an issue
* `pm start <id> [deadline]` - mark issue as in-progress, with optional deadline (in humanized form - e.g. `in 2 days`)
* `pm backlog <id>` - places issue back in the backlog
* `pm end <id>` - mark issue as completed
* `pm commit <id>` - mark issue as completed and commit changes to git using issue text for message
* `pm tag [-r] <tag> <id>` - add/remove a tag to/from an issue
* `pm feature [-r] <tag>` - flags/unflags a tag as a feature (used to group issues in list display)
* `pm plan [tag]` - open an editor for entering multiple issues, optionally tagged with `<tag>`
* `pm remote [-r] <plugin>` - set up (or remove) a two-way sync with a remote system (e.g. 'github')

*Planned*

* `pm start random` - start a random backlog issue, for those moments of indecision

## GitHub

TeenyPM can also push and pull issues to and from a GitHub repo issues store. To configure this run:

`pm remote github`

You will need a GitHub Personal Access Token with repo access (https://github.com/settings/tokens).

After configuring the integration, teenypm will pull any issues present in the repo and create issues from them. It will also push issues that exist locally into GitHub.

When interacting with issues in teenypm you need to use the teenypm issue id and not the GitHub issue number.

For performance, teenypm will not look for new issues in the remote repo on every use. Instead it will wait for more than an hour to pass since the last sync time. To force it to pull remote issues you can pass the `-s` flag.

Write operations (e.g. adding, modifying or changing an issue state) will immediately push changes to the remote repo.

## Configuration

The editor used for `edit`ing and `plan`ing defaults to `vim`.

You can specify an alternative by setting the `EDITOR` environment variable.

Additionally, if the command string contains the optional string `<file>` it will be replaced with the temporary filename, and the string `<line>` will replaced with the line number with which to set the cursor.

For example, to use VS Code:

`export EDITOR="code --wait --new-window -g<file>:<line>"`

(Assumes that the `code` command has been installed from VS Code - see https://code.visualstudio.com/docs/setup/mac#_launching-from-the-command-line.)
