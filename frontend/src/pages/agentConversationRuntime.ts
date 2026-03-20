type RuntimeChunk = {
  is_new_runtime?: boolean;
  restored_from_snapshot?: boolean;
};

type Translate = (key: string, fallback: string) => string;

export function getRuntimeStatusMessage(
  chunk: RuntimeChunk,
  translate: Translate,
): string | null {
  if (!chunk.is_new_runtime) {
    return null;
  }

  return chunk.restored_from_snapshot
    ? translate('agent.runtimeRestored', 'Runtime restored from the latest snapshot.')
    : translate('agent.runtimeFresh', 'Runtime started for this conversation.');
}
