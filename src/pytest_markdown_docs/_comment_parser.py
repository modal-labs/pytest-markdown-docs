"""
Inspired by markdown-it-py and its plugins:
    https://github.com/executablebooks/markdown-it-py/blob/master/markdown_it/rules_block/fence.py
    https://github.com/executablebooks/markdown-it-py/blob/master/markdown_it/rules_block/html_block.py
    https://github.com/executablebooks/mdit-py-plugins/blob/master/mdit_py_plugins/admon/index.py

MIT License Copyright (c) 2020 ExecutableBookProject
"""

from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock

MARKERS = (
    ("<!--~~~", "~~~-->"),
    ("<!--```", "```-->"),
)
LEN_OPENING_MARKER = len(MARKERS[0][0])


def comment(state: StateBlock, startLine: int, endLine: int, silent: bool) -> bool:
    """
    A rule to parse comments in markdown files.
    """
    if state.is_code_block(startLine):
        return False

    line_start = state.bMarks[startLine] + state.tShift[startLine]
    line_end = state.eMarks[startLine]

    if line_start + LEN_OPENING_MARKER > line_end:
        return False

    # Fast check to fail if first character doesn't match
    if state.src[line_start] != "<":
        return False

    try:
        marker = state.src[line_start : line_start + LEN_OPENING_MARKER]
    except IndexError:
        return False

    for start_marker in MARKERS:
        if marker == start_marker[0]:
            end_marker = start_marker[1]
            break
    else:
        return False

    # Since start is found, we can report success here in validation mode
    if silent:
        return True

    params = state.src[line_start + LEN_OPENING_MARKER : line_end]

    # search end of block
    nextLine = startLine

    haveEndMarker = False
    while nextLine < endLine - 1:
        nextLine += 1
        line_start = state.bMarks[nextLine] + state.tShift[nextLine]
        line_end = state.eMarks[nextLine]

        if line_start < line_end and state.sCount[nextLine] < state.blkIndent:
            # non-empty line with negative indent should stop the list:
            # - ```
            #  test
            break

        if state.is_code_block(nextLine):
            continue

        try:
            if state.src[line_start : line_start + len(end_marker)] != end_marker:
                continue
        except IndexError:
            break

        

        # make sure tail has spaces only
        pos = state.skipSpaces(line_start + len(end_marker))
        if pos < line_end:
            continue

        haveEndMarker = True
        # found!
        break

    # If a fence has heading spaces, they should be removed from its inner block
    length = state.sCount[startLine]

    state.line = nextLine + (1 if haveEndMarker else 0)

    token = state.push("fence", "code", 0)
    token.info = params
    token.content = state.getLines(startLine + 1, nextLine, length, True)
    token.markup = marker
    token.map = [startLine, state.line]

    return True


def comment_plugin(md: MarkdownIt, render=None) -> None:
    md.block.ruler.before("html_block", "comment", comment)
