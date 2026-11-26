#!/bin/sh
# run the linux test build under a virtual display: tools/xrun.sh --script runs/x.txt --shots runs/x ...
exec docker run --rm -v "$(pwd)":/w -w /w -e LIBGL_ALWAYS_SOFTWARE=1 oop-test \
    xvfb-run -a -s "-screen 0 1920x1080x24" ./build/oop-test --fast "$@"
