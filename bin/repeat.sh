#!/bin/bash
function repeat() {
    number=$1
    shift
    for n in $(seq $number); do
        echo ""
        echo "the $n time"
        $@
    done
}
repeat $@
