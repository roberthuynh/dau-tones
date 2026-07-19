import { useCallback, useRef, useState } from "react";

export const MICROPHONE_PRIVACY_VERSION = "2026-07-19.2";
export const MICROPHONE_PRIVACY_STORAGE_KEY = "dau-microphone-privacy";

export type MicrophoneIntent = "tone_shapes" | "dialogue";
export type MicrophoneAction = () => void | Promise<void>;
export type RequestMicrophoneAccess = (intent: MicrophoneIntent, action: MicrophoneAction) => void;

type StoredPrivacyChoice = {
  version: string;
  modes: Partial<Record<MicrophoneIntent, { acknowledged_at: string }>>;
};

type PendingMicrophoneAction = {
  intent: MicrophoneIntent;
  action: MicrophoneAction;
};

function storedPrivacyChoice(storage: Pick<Storage, "getItem">): StoredPrivacyChoice | null {
  try {
    const stored = JSON.parse(storage.getItem(MICROPHONE_PRIVACY_STORAGE_KEY) ?? "null") as StoredPrivacyChoice | null;
    return stored?.version === MICROPHONE_PRIVACY_VERSION && stored.modes ? stored : null;
  } catch {
    return null;
  }
}

export function hasCurrentMicrophoneAcknowledgement(intent: MicrophoneIntent, storage: Pick<Storage, "getItem"> = window.localStorage): boolean {
  return Boolean(storedPrivacyChoice(storage)?.modes[intent]);
}

export function saveMicrophoneAcknowledgement(
  intent: MicrophoneIntent,
  storage: Pick<Storage, "getItem" | "setItem"> = window.localStorage,
): void {
  try {
    const current = storedPrivacyChoice(storage);
    const choice: StoredPrivacyChoice = {
      version: MICROPHONE_PRIVACY_VERSION,
      modes: {
        ...current?.modes,
        [intent]: { acknowledged_at: new Date().toISOString() },
      },
    };
    storage.setItem(MICROPHONE_PRIVACY_STORAGE_KEY, JSON.stringify(choice));
  } catch {
    // Private browsing and locked-down storage should not block microphone use.
  }
}

export function useMicrophonePrivacy() {
  const [open, setOpen] = useState(false);
  const [intent, setIntent] = useState<MicrophoneIntent | null>(null);
  const [acknowledged, setAcknowledged] = useState<Record<MicrophoneIntent, boolean>>(() => ({
    tone_shapes: hasCurrentMicrophoneAcknowledgement("tone_shapes"),
    dialogue: hasCurrentMicrophoneAcknowledgement("dialogue"),
  }));
  const pendingRef = useRef<PendingMicrophoneAction | null>(null);

  const requestMicrophoneAccess = useCallback<RequestMicrophoneAccess>((nextIntent, action) => {
    if (acknowledged[nextIntent] || hasCurrentMicrophoneAcknowledgement(nextIntent)) {
      setAcknowledged((current) => ({ ...current, [nextIntent]: true }));
      void action();
      return;
    }
    pendingRef.current = { intent: nextIntent, action };
    setIntent(nextIntent);
    setOpen(true);
  }, [acknowledged]);

  const acknowledgeAndContinue = useCallback(() => {
    const pending = pendingRef.current;
    if (!pending) return;
    saveMicrophoneAcknowledgement(pending.intent);
    setAcknowledged((current) => ({ ...current, [pending.intent]: true }));
    setOpen(false);
    pendingRef.current = null;
    setIntent(null);
    if (pending) void pending.action();
  }, []);

  const close = useCallback(() => {
    pendingRef.current = null;
    setIntent(null);
    setOpen(false);
  }, []);

  const openDisclosure = useCallback(() => {
    pendingRef.current = null;
    setIntent(null);
    setOpen(true);
  }, []);

  return {
    open,
    intent,
    acknowledged,
    requestMicrophoneAccess,
    acknowledgeAndContinue,
    close,
    openDisclosure,
  };
}
