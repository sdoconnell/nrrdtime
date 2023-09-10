---
title: NRRDTIME
section: 1
header: User Manual
footer: nrrdtime 0.0.2
date: January 3, 2022
---
# NAME
nrrdtime - Terminal-based time tracking for nerds.

# SYNOPSIS
**nrrdtime** *command* [*OPTION*]...

# DESCRIPTION
**nrrdtime** is a terminal-based time tracking program with advanced search options, formatted output, and time entry data stored in local text files. It can be run in either of two modes: command-line or interactive shell.

# OPTIONS
**-h**, **--help**
: Display help information.

**-c**, **--config** *file*
: Use a non-default configuration file.

# COMMANDS
**nrrdtime** provides the following commands.

**config**
: Edit the **nrrdtime** configuration file.

**delete (rm)** *alias* [*OPTION*]
: Delete a time entry and entry file. The user will be prompted for confirmation.

    *OPTIONS*

    **-f**, **--force**
    : Force deletion, do not prompt for confirmation.


**edit** *alias*
: Edit a time entry file in the user's editor (defined by the $EDITOR environment variable). If $EDITOR is not defined, an error message will report that.

**info** *alias* [*OPTION*]
: Show the full details about a time entry.

    *OPTIONS*

    **-p**, **--page**
    : Page the command output through $PAGER.


**list (ls)** *view* [*OPTION*]
: List time entries matching one of the following views:

    - *all* : All time entries (running and paused).
    - *paused* : Paused time entries.
    - *running* : Running time entries.

    *OPTIONS*

    **-p**, **--page**
    : Page the command output through $PAGER.

**modify (mod)** *alias* [*OPTION*]...
: Modify a time entry.

    *OPTIONS*

    **--completed** *YYYY-MM-DD[ HH:MM]*
    : The time entry completed date(time).

    **--description** *text*
    : The time entry description.

    **--notes** *text*
    : Notes to add to the time entry. Be sure to properly escape the text if it includes special characters or newlines that may be interpretted by the shell. Using this option, any existing notes on the time entry will be replaced. This command option is included mainly for the purpose of automated note insertion (i.e., via script or command). For more reliable note editing, use the **notes** command.
    
    **--project** *project*
    : The project associated with this time entry.

    **--started** *YYYY-MM-DD[ HH:MM]*
    : The time entry started date(time).

    **--status** *status*
    : The time entry status. The following statuses are recognized by **nrrdtime**:

        - *stopped* : the time entry is completed.
        - *running* : the time entry is running.
        - *paused* : the time entry is paused.

    **--tags** *tag[,tag]*
    : Tags assigned to the time entry. This can be a single tag or multiple tags in a comma-delimited list. Normally with this option, any existing tags assigned to the time entry will be replaced. However, this option also supports two special operators: **+** (add a tag to the existing tags) and **~** (remove a tag from the existing tags). For example, *--tags +documentation* will add the *documentation* tag to the existing tags on a time entry, and *--tags ~testing,experimental* will remove both the *testing* and *experimental* tags from a time entry.

    **--del-time** *index*
    : Delete a clock line from a time entry. The clock line is identified by the index displayed in the output of **info**.

**notes** *alias*
: Add or update notes on a time entry using the user's editor (defined by the $EDITOR environment variable). If $EDITOR is not defined, an error message will report that.

**pause** *alias*
: Pause a running time entry.

**query** *searchterm* [*OPTION*]...
: Search for one or more time entries and produce plain text output (by default, tab-delimited text).

    *OPTIONS*

    **-l**, **--limit**
    : Limit the output to one or more specific fields (provided as a comma-delimited list).

    **-j**, **--json**
    : Output in JSON format rather than the default tab-delimited format.


**report** *searchterm* [*OPTION*]
: Produce a time report based on the given criteria. The *searchterm* can be in the same format as **query**, or can be one of: *today*, *yesterday*, *thisweek*, *lastweek*, *thismonth*, *lastmonth*, *thisyear*, or *lastyear*.

    *OPTIONS*

    **-p**, **--page**
    : Page the command output through $PAGER.


**resume** *alias*
: Resume a paused time entry.

**shell**
: Launch the **nrrdtime** interactive shell.

**start** *description* [*OPTION*]...
: Start a new time entry.

    *OPTIONS*

    **--project** *project*
    : The project associated with this time entry.

    **--tags** *tag[,tag]*
    : Tags assigned to the time entry. See the **--tags** option of **modify**.


**stop** *alias*
: Stop (and complete) a running time entry.

**unset** *alias* *field*
: Clear a field from a specified time entry.

**version**
: Show the application version information.

# NOTES

## Report and query
There are two command-line methods for filtering the presented list of time entries: **report** and **query**.

**report** produces a time report in a tabular, human-readable format. Query results are presented in the form of tab-delimited text (by default) or JSON (if using the *-j* or *--json* option) and are primarily intended for use by other programs that are able to consume structured text output.

**report** and **query** use the same filter syntax. The most basic form of filtering is to simply search for a keyword or string in the time entry description:

    nrrdtime report <search_term>

**NOTE:** search terms are case-insensitive.

If the search term is present in the time entry *description*, the time entry will be displayed.

Optionally, a search type may be specified. The search type may be one of *uid*, *alias*, *description*, *project*, *tags*, *status*, *started*, *completed*, or *notes*. If an invalid search type is provided, the search type will default to *description*. To specify a search type, use the format:

    nrrdtime report [search_type=]<search_term>

You may combine search types in a comma-delimited structure. All search criteria must be met to return a result.

The tags search type may also use the optional **+** operator to search for more than one tag. Any matched tag will return a result.

The special search term *any* can be used to match all time entries, but is only useful in combination with an exclusion to match all records except those excluded.

## Exclusion
In addition to the search term, an exclusion term may be provided. Any match in the exclusion term will negate a match in the search term. An exclusion term is formatted in the same manner as the search term, must follow the search term, and must be denoted using the **%** operator:

    nrrdtime report [search_type=]<search_term>%[exclusion_type=]<exclusion_term>

## Search examples
Search for any time entry description with the word "projectx":

    nrrdtime report projectx

Search for any time entries completed 2021-11-15:

    nrrdtime report completed=2021-11-15

Search for all time entries tagged "development" or "testing" with a status of "stopped", except for those that are tagged "nonbill":

    nrrdtime report status=stopped,tags=development+testing%tags=nonbill

## Query and limit
The **query** function uses the same syntax as **report** but will output information in a form that may be read by other programs. The standard fields returned by query for tab-delimited output are:

    - uid (string)
    - alias (string)
    - status (string)
    - started (string)
    - completed (string)
    - time (string)
    - description (string)
    - project (string)
    - tags (list)

List fields are returned in standard Python format: ['item 1', 'item 2', ...]. Empty lists are returned as []. Empty string fields will appear as multiple tabs.

JSON output returns all fields for a record, including fields not provided in tab-delimited output.

The query function may also use the **--limit** (**-l**) option. This is a comma-separated list of fields to return. The **--limit** option does not have an effect on JSON output.

## Paging
Output from **list**, **report**, and **info** can get long and run past your terminal buffer. You may use the **-p**, **--page** option in conjunction with report, list, or info to page output.


# FILES
**~/.config/nrrdtime/config**
: Default configuration file

**~/.local/share/nrrdtime**
: Default data directory

# AUTHORS
Written by Sean O'Connell <https://sdoconnell.net>.

# BUGS
Submit bug reports at: <https://github.com/sdoconnell/nrrdtime/issues>

# SEE ALSO
Further documentation and sources at: <https://github.com/sdoconnell/nrrdtime>
