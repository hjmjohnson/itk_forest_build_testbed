from enum import StrEnum


class Reason(StrEnum):
    LOOP_CARRIED = "loop-carried"
    COSTLY_CONSTRUCT = "costly-construct"
    TRY_READ_AFTER = "try-read-after"
    PREPROCESSOR = "preprocessor"
    GOTO_OR_CASE = "goto-or-case"
    NARROWING = "narrowing"
    INIT_LIST_CTOR = "init-list-ctor"
    STATIC_LOCAL = "static-local"
    ORDER_VIOLATION = "order-violation"
    NO_INCLUDING_TU = "no-including-tu"
    COMMENT_STRANDED = "comment-stranded"
    GATE_FAILED = "gate-failed"
    ITK_VERSION = "itk-version"
