#/usr/bin/env bash
# bash completion for nrrdtime

shopt -s progcomp
_nrrdtime() {
    local cur prev firstword complete_options
    
    cur=$2
    prev=$3
	firstword=$(__get_firstword)

	GLOBAL_OPTIONS="\
        config\
        delete\
        edit\
        info\
        list\
        modify\
        notes\
        pause\
        query\
        report\
        resume\
        shell\
        start\
        stop\
        unset\
        version\
        --config\
        --help"

    CONFIG_OPTIONS="--help"
    DELETE_OPTIONS="--help --force"
    EDIT_OPTIONS="--help"
    INFO_OPTIONS="--help --page"
    LIST_OPTIONS="--help --page"
    MODIFY_OPTIONS="--help"
    MODIFY_OPTIONS_WA="\
        --completed\
        --description\
        --notes\
        --project\
        --started\
        --status\
        --tags\
        --del-time"
    NOTES_OPTIONS="--help"
    PAUSE_OPTIONS="--help"
    QUERY_OPTIONS="--help --json"
    QUERY_OPTIONS_WA="--limit"
    REPORT_OPTIONS="--help"
    RESUME_OPTIONS="--help"
    SHELL_OPTIONS="--help"
    START_OPTIONS="--help"
    START_OPTIONS_WA="\
        --project\
        --tags"
    STOP_OPTIONS="--help"
    UNSET_OPTIONS="--help"
    VERSION_OPTIONS="--help"

	case "${firstword}" in
 	config)
		complete_options="$CONFIG_OPTIONS"
		complete_options_wa=""
		;;
	delete)
		complete_options="$DELETE_OPTIONS"
		complete_options_wa=""
		;;
	edit)
		complete_options="$EDIT_OPTIONS"
		complete_options_wa=""
		;;
	info)
		complete_options="$INFO_OPTIONS"
		complete_options_wa=""
		;;
	list)
		complete_options="$LIST_OPTIONS"
		complete_options_wa=""
		;;
	modify)
		complete_options="$MODIFY_OPTIONS"
		complete_options_wa="$MODIFY_OPTIONS_WA"
		;;
	notes)
		complete_options="$NOTES_OPTIONS"
		complete_options_wa=""
		;;
	pause)
		complete_options="$PAUSE_OPTIONS"
		complete_options_wa=""
		;;
	query)
		complete_options="$QUERY_OPTIONS"
		complete_options_wa="$QUERY_OPTIONS_WA"
		;;
	report)
		complete_options="$REPORT_OPTIONS"
		complete_options_wa=""
		;;
	resume)
		complete_options="$RESUME_OPTIONS"
		complete_options_wa=""
		;;
 	shell)
		complete_options="$SHELL_OPTIONS"
		complete_options_wa=""
		;;
 	start)
		complete_options="$START_OPTIONS"
		complete_options_wa=""
		;;
 	stop)
		complete_options="$STOP_OPTIONS"
		complete_options_wa=""
		;;
	unset)
		complete_options="$UNSET_OPTIONS"
		complete_options_wa=""
		;;
	version)
		complete_options="$VERSION_OPTIONS"
		complete_options_wa=""
		;;

	*)
        complete_options="$GLOBAL_OPTIONS"
        complete_options_wa=""
		;;
	esac


    for opt in "${complete_options_wa}"; do
        [[ $opt == $prev ]] && return 1 
    done

    all_options="$complete_options $complete_options_wa"
    COMPREPLY=( $( compgen -W "$all_options" -- $cur ))
	return 0
}

__get_firstword() {
	local firstword i
 
	firstword=
	for ((i = 1; i < ${#COMP_WORDS[@]}; ++i)); do
		if [[ ${COMP_WORDS[i]} != -* ]]; then
			firstword=${COMP_WORDS[i]}
			break
		fi
	done
 
	echo $firstword
}
 
complete -F _nrrdtime nrrdtime
