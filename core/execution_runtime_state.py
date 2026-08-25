EXECUTION_RUNTIME_META_KEY = "execution_runtime_state_v1"


def persist_execution_runtime_state(bot) -> None:
    brain = getattr(bot, "brain", None)
    execution = getattr(bot, "execution", None)
    if brain is None or execution is None:
        return

    exporter = getattr(execution, "export_runtime_state", None)
    setter = getattr(brain, "set_metadata_json", None)
    if not callable(exporter) or not callable(setter):
        return

    try:
        state = exporter() or {}
        setter(EXECUTION_RUNTIME_META_KEY, state)
    except Exception as error:
        log_fn = getattr(bot, "log", None)
        if callable(log_fn):
            log_fn(f"⚠️ Error persistiendo execution runtime state: {error}")


def load_execution_runtime_state(bot) -> None:
    brain = getattr(bot, "brain", None)
    execution = getattr(bot, "execution", None)
    if brain is None or execution is None:
        return

    getter = getattr(brain, "get_metadata_json", None)
    importer = getattr(execution, "import_runtime_state", None)
    if not callable(getter) or not callable(importer):
        return

    try:
        state = getter(EXECUTION_RUNTIME_META_KEY, default={}) or {}
        importer(state)
    except Exception as error:
        log_fn = getattr(bot, "log", None)
        if callable(log_fn):
            log_fn(f"⚠️ Error restaurando execution runtime state: {error}")
